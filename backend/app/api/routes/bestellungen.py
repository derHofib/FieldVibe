from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_module, require_roles
from app.models.bestellung import Bestellung, BestellungPosition
from app.models.lieferant import Lieferant
from app.models.material import Material
from app.models.material_bedarf import MaterialBedarf
from app.models.vorgang_event import VorgangEvent
from app.schemas.bestellung import BestellungAusBedarfenCreate, BestellungRead, BestellungUpdate
from app.services import papierkorb_service
from app.services.bestellung_service import apply_status_transition, positionen_fuer, to_read_model
from app.services.csv_service import csv_response
from app.services.numbering_service import next_bestellnummer
from app.services.pdf_service import generate_bestellung_pdf

# loesch_operativ hat ueberall dieselben Rechte wie mandant_admin (siehe
# app/api/deps.py:require_roles()) und braucht daher wie dieser Zugriff auf
# diesen Router.
router = APIRouter(
    prefix="/api/bestellungen",
    tags=["bestellungen"],
    dependencies=[
        Depends(require_roles("mandant_admin", "disponent", "loesch_operativ")),
        Depends(require_module("material")),
    ],
)


@router.get("", response_model=list[BestellungRead])
async def list_bestellungen(session: AsyncSession = Depends(get_db)) -> list[BestellungRead]:
    result = await session.execute(
        select(Bestellung)
        .where(Bestellung.geloescht_am.is_(None))
        .order_by(Bestellung.created_at.desc())
    )
    return [await to_read_model(session, b) for b in result.scalars().all()]


@router.get("/{bestellung_id}", response_model=BestellungRead)
async def get_bestellung(bestellung_id: UUID, session: AsyncSession = Depends(get_db)) -> BestellungRead:
    bestellung = await session.get(Bestellung, bestellung_id)
    if bestellung is None or bestellung.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bestellung nicht gefunden")
    return await to_read_model(session, bestellung)


@router.delete("/{bestellung_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bestellung(
    bestellung_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    bestellung = await papierkorb_service.soft_delete(
        session, entity_typ="bestellung", entity_id=bestellung_id, actor_user_id=auth.user_id
    )
    if bestellung is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bestellung nicht gefunden")


@router.post(
    "/from-bedarfe",
    response_model=BestellungRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_bestellung_from_bedarfe(
    body: BestellungAusBedarfenCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> BestellungRead:
    if not body.material_bedarf_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Keine Materialbedarfe angegeben")

    bedarfe: list[MaterialBedarf] = []
    for bedarf_id in body.material_bedarf_ids:
        bedarf = await session.get(MaterialBedarf, bedarf_id)
        if bedarf is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Materialbedarf {bedarf_id} nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
        if bedarf.status != "offen" or bedarf.zweck != "bestellung":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Materialbedarf {bedarf_id} ist nicht als offener Bestell-Bedarf verfügbar",
            )
        bedarfe.append(bedarf)

    if body.lieferant_id is not None and await session.get(Lieferant, body.lieferant_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lieferant nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )

    # Mehrere Bedarfe desselben Materials (z.B. aus verschiedenen
    # Auftraegen) werden zu einer Position zusammengefasst -- eine
    # Sammelbestellung soll nicht dieselbe Artikelnummer mehrfach auflisten.
    mengen_je_material: dict[UUID, Decimal] = defaultdict(Decimal)
    for bedarf in bedarfe:
        mengen_je_material[bedarf.material_id] += bedarf.menge

    materialien = {
        m.id: m
        for m in (
            await session.execute(select(Material).where(Material.id.in_(mengen_je_material.keys())))
        )
        .scalars()
        .all()
    }

    bestellnummer = await next_bestellnummer(session, auth.mandant_id)
    bestellung = Bestellung(
        mandant_id=auth.mandant_id,
        lieferant_id=body.lieferant_id,
        bestellnummer=bestellnummer,
        erstellt_von=auth.user_id,
        notiz=body.notiz,
    )
    session.add(bestellung)
    await session.flush()

    for i, (material_id, menge) in enumerate(mengen_je_material.items()):
        material = materialien[material_id]
        session.add(
            BestellungPosition(
                mandant_id=auth.mandant_id,
                bestellung_id=bestellung.id,
                material_id=material_id,
                position=i + 1,
                beschreibung=material.bezeichnung,
                menge=menge,
                einheit=material.einheit,
                einzelpreis=material.einzelpreis or Decimal("0"),
            )
        )

    vorgang_ids = set()
    for bedarf in bedarfe:
        bedarf.status = "bestellt"
        bedarf.bestellung_id = bestellung.id
        vorgang_ids.add(bedarf.vorgang_id)

    for vid in vorgang_ids:
        session.add(
            VorgangEvent(
                mandant_id=auth.mandant_id,
                vorgang_id=vid,
                event_type="material",
                author_user_id=auth.user_id,
                body=f"Bestellung {bestellnummer} erzeugt",
                payload={"bestellung_id": str(bestellung.id)},
            )
        )

    await session.flush()
    await session.refresh(bestellung)
    return await to_read_model(session, bestellung)


@router.patch(
    "/{bestellung_id}",
    response_model=BestellungRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def update_bestellung(
    bestellung_id: UUID,
    body: BestellungUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> BestellungRead:
    bestellung = await session.get(Bestellung, bestellung_id)
    if bestellung is None or bestellung.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bestellung nicht gefunden")

    if body.lieferant_id is not None:
        if await session.get(Lieferant, body.lieferant_id) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lieferant nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
        bestellung.lieferant_id = body.lieferant_id
    if body.notiz is not None:
        bestellung.notiz = body.notiz
    if body.status is not None:
        await apply_status_transition(session, bestellung, body.status, erstellt_von=auth.user_id)

    await session.flush()
    await session.refresh(bestellung)
    return await to_read_model(session, bestellung)


@router.get("/{bestellung_id}/csv")
async def bestellung_csv(bestellung_id: UUID, session: AsyncSession = Depends(get_db)) -> Response:
    bestellung = await session.get(Bestellung, bestellung_id)
    if bestellung is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bestellung nicht gefunden")
    positionen = await positionen_fuer(session, bestellung_id)

    rows = [[p.position, p.beschreibung, f"{p.menge:g}", p.einheit, f"{p.einzelpreis:g}"] for p in positionen]
    return csv_response(
        ["Position", "Beschreibung", "Menge", "Einheit", "Richtwert Einzelpreis"],
        rows,
        f"{bestellung.bestellnummer}.csv",
    )


@router.get("/{bestellung_id}/pdf")
async def bestellung_pdf(
    bestellung_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    bestellung = await session.get(Bestellung, bestellung_id)
    if bestellung is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bestellung nicht gefunden")
    lieferant = await session.get(Lieferant, bestellung.lieferant_id) if bestellung.lieferant_id else None
    positionen = await positionen_fuer(session, bestellung_id)
    from app.models.mandant import Mandant

    mandant = await session.get(Mandant, auth.mandant_id)

    pdf_bytes = generate_bestellung_pdf(mandant, bestellung, positionen, lieferant)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{bestellung.bestellnummer}.pdf"'},
    )
