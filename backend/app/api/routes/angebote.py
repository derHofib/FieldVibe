from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AuthContext,
    get_current_user,
    get_db,
    require_module,
    require_recht,
    require_roles,
)
from app.models.angebot import Angebot, AngebotPosition
from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.mangel import Mangel
from app.models.material import Material
from app.models.material_bedarf import MaterialBedarf
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.angebot import (
    AngebotAusMaengelnCreate,
    AngebotAusMaterialBedarfenCreate,
    AngebotCreate,
    AngebotPositionCreate,
    AngebotRead,
    AngebotUpdate,
)
from app.services import papierkorb_service
from app.services.angebot_service import apply_status_transition, positionen_fuer, to_read_model
from app.services.numbering_service import next_angebotsnummer
from app.services.pdf_service import generate_angebot_pdf

router = APIRouter(
    prefix="/api/angebote",
    tags=["angebote"],
    dependencies=[
        Depends(
            require_roles(
                "mandant_admin", "disponent", "techniker", "controller", "mitarbeiter",
                "loesch_operativ",
            )
        ),
        Depends(require_module("abrechnung")),
        Depends(require_recht("abrechnung", "sehen")),
    ],
)


@router.get("", response_model=list[AngebotRead])
async def list_angebote(
    kunde_id: UUID | None = Query(default=None),
    vorgang_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_db),
) -> list[AngebotRead]:
    stmt = select(Angebot).where(Angebot.geloescht_am.is_(None)).order_by(Angebot.created_at.desc())
    if kunde_id:
        stmt = stmt.where(Angebot.kunde_id == kunde_id)
    if vorgang_id:
        stmt = stmt.where(Angebot.vorgang_id == vorgang_id)
    if status_filter:
        stmt = stmt.where(Angebot.status == status_filter)
    result = await session.execute(stmt)
    return [await to_read_model(session, a) for a in result.scalars().all()]


@router.get("/{angebot_id}", response_model=AngebotRead)
async def get_angebot(angebot_id: UUID, session: AsyncSession = Depends(get_db)) -> AngebotRead:
    angebot = await session.get(Angebot, angebot_id)
    if angebot is None or angebot.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Angebot nicht gefunden")
    return await to_read_model(session, angebot)


@router.delete(
    "/{angebot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "loesch_operativ"))],
)
async def delete_angebot(
    angebot_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    angebot = await session.get(Angebot, angebot_id)
    if angebot is None or angebot.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Angebot nicht gefunden")
    if angebot.status != "entwurf":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nur Angebote im Entwurf können gelöscht werden",
        )
    await papierkorb_service.soft_delete(
        session, entity_typ="angebot", entity_id=angebot_id, actor_user_id=auth.user_id
    )


async def _validate_kunde_vorgang(session: AsyncSession, kunde_id: UUID, vorgang_id: UUID | None) -> None:
    if await session.get(Kunde, kunde_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kunde nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if vorgang_id is not None:
        vorgang = await session.get(Vorgang, vorgang_id)
        if vorgang is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
        if vorgang.kunde_id != kunde_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Vorgang gehört nicht zum angegebenen Kunden"
            )


def _neue_positionen(angebot_id: UUID, mandant_id: UUID, eintraege: list[AngebotPositionCreate]) -> list[AngebotPosition]:
    return [
        AngebotPosition(
            mandant_id=mandant_id,
            angebot_id=angebot_id,
            position=i + 1,
            beschreibung=e.beschreibung,
            menge=e.menge,
            einheit=e.einheit,
            einzelpreis=e.einzelpreis,
        )
        for i, e in enumerate(eintraege)
    ]


@router.post(
    "",
    response_model=AngebotRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_angebot(
    body: AngebotCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AngebotRead:
    await _validate_kunde_vorgang(session, body.kunde_id, body.vorgang_id)

    angebotsnummer = await next_angebotsnummer(session, auth.mandant_id)
    angebot = Angebot(
        mandant_id=auth.mandant_id,
        kunde_id=body.kunde_id,
        vorgang_id=body.vorgang_id,
        angebotsnummer=angebotsnummer,
        erstellt_von=auth.user_id,
        gueltig_bis=body.gueltig_bis,
    )
    session.add(angebot)
    await session.flush()

    for p in _neue_positionen(angebot.id, auth.mandant_id, body.positionen):
        session.add(p)
    await session.flush()
    await session.refresh(angebot)
    return await to_read_model(session, angebot)


@router.post(
    "/from-maengel",
    response_model=AngebotRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_angebot_from_maengel(
    body: AngebotAusMaengelnCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AngebotRead:
    if not body.mangel_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Keine Mängel angegeben")

    maengel: list[Mangel] = []
    for mangel_id in body.mangel_ids:
        mangel = await session.get(Mangel, mangel_id)
        if mangel is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Mangel {mangel_id} nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
        if mangel.status != "offen":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Mangel {mangel_id} ist nicht offen (Status: {mangel.status})",
            )
        maengel.append(mangel)

    vorgang_ids = {m.vorgang_id for m in maengel}
    vorgaenge = {vid: await session.get(Vorgang, vid) for vid in vorgang_ids}
    kunde_ids = {v.kunde_id for v in vorgaenge.values() if v is not None}
    if len(kunde_ids) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Alle Mängel müssen zum selben Kunden gehören",
        )
    kunde_id = next(iter(kunde_ids))
    # Ein gemeinsamer Vorgang wird uebernommen, wenn alle Maengel aus
    # demselben Vorgang stammen -- sonst bleibt vorgang_id leer und die
    # Verknuepfung laeuft ausschliesslich ueber die einzelnen Maengel.
    gemeinsamer_vorgang_id = next(iter(vorgang_ids)) if len(vorgang_ids) == 1 else None

    angebotsnummer = await next_angebotsnummer(session, auth.mandant_id)
    angebot = Angebot(
        mandant_id=auth.mandant_id,
        kunde_id=kunde_id,
        vorgang_id=gemeinsamer_vorgang_id,
        angebotsnummer=angebotsnummer,
        erstellt_von=auth.user_id,
        gueltig_bis=body.gueltig_bis,
    )
    session.add(angebot)
    await session.flush()

    # Einzelpreis startet bei 0 -- der Mangeltext beschreibt das Problem,
    # nicht dessen Marktpreis; der Disponent traegt die Kalkulation vor dem
    # Versenden nach, wie auf einem Papier-Angebot auch.
    positionen = [
        AngebotPositionCreate(beschreibung=m.beschreibung, menge=Decimal("1"), einheit="Stk", einzelpreis=Decimal("0"))
        for m in maengel
    ]
    for p in _neue_positionen(angebot.id, auth.mandant_id, positionen):
        session.add(p)

    for mangel in maengel:
        mangel.angebot_id = angebot.id
        mangel.status = "in_angebot"

    for vid in vorgang_ids:
        session.add(
            VorgangEvent(
                mandant_id=auth.mandant_id,
                vorgang_id=vid,
                event_type="angebot",
                author_user_id=auth.user_id,
                body=f"Angebot {angebotsnummer} aus {len(maengel)} Mangel/Mängeln erstellt",
                payload={"angebot_id": str(angebot.id), "status": "entwurf"},
            )
        )

    await session.flush()
    await session.refresh(angebot)
    return await to_read_model(session, angebot)


@router.post(
    "/from-material-bedarfe",
    response_model=AngebotRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_angebot_from_material_bedarfe(
    body: AngebotAusMaterialBedarfenCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AngebotRead:
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
        if bedarf.status != "offen" or bedarf.zweck != "angebot":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Materialbedarf {bedarf_id} ist nicht als offener Angebots-Bedarf verfügbar",
            )
        bedarfe.append(bedarf)

    vorgang_ids = {b.vorgang_id for b in bedarfe}
    vorgaenge = {vid: await session.get(Vorgang, vid) for vid in vorgang_ids}
    kunde_ids = {v.kunde_id for v in vorgaenge.values() if v is not None}
    if len(kunde_ids) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Alle Materialbedarfe müssen zum selben Kunden gehören",
        )
    kunde_id = next(iter(kunde_ids))
    gemeinsamer_vorgang_id = next(iter(vorgang_ids)) if len(vorgang_ids) == 1 else None

    # Mehrere Bedarfe desselben Materials (z.B. aus verschiedenen
    # Auftraegen) werden zu einer Position zusammengefasst -- ein Angebot
    # soll dieselbe Artikelbezeichnung nicht mehrfach auflisten, siehe
    # dieselbe Logik in create_bestellung_from_bedarfe.
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

    angebotsnummer = await next_angebotsnummer(session, auth.mandant_id)
    angebot = Angebot(
        mandant_id=auth.mandant_id,
        kunde_id=kunde_id,
        vorgang_id=gemeinsamer_vorgang_id,
        angebotsnummer=angebotsnummer,
        erstellt_von=auth.user_id,
        gueltig_bis=body.gueltig_bis,
    )
    session.add(angebot)
    await session.flush()

    positionen = [
        AngebotPositionCreate(
            beschreibung=materialien[material_id].bezeichnung,
            menge=menge,
            einheit=materialien[material_id].einheit,
            einzelpreis=materialien[material_id].einzelpreis or Decimal("0"),
        )
        for material_id, menge in mengen_je_material.items()
    ]
    for p in _neue_positionen(angebot.id, auth.mandant_id, positionen):
        session.add(p)

    for bedarf in bedarfe:
        bedarf.angebot_id = angebot.id
        bedarf.status = "in_angebot"

    for vid in vorgang_ids:
        session.add(
            VorgangEvent(
                mandant_id=auth.mandant_id,
                vorgang_id=vid,
                event_type="angebot",
                author_user_id=auth.user_id,
                body=f"Angebot {angebotsnummer} aus {len(bedarfe)} Materialbedarf(en) erstellt",
                payload={"angebot_id": str(angebot.id), "status": "entwurf"},
            )
        )

    await session.flush()
    await session.refresh(angebot)
    return await to_read_model(session, angebot)


@router.post(
    "/{angebot_id}/positionen",
    response_model=AngebotRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def add_position(
    angebot_id: UUID,
    body: AngebotPositionCreate,
    session: AsyncSession = Depends(get_db),
) -> AngebotRead:
    angebot = await session.get(Angebot, angebot_id)
    if angebot is None or angebot.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Angebot nicht gefunden")
    if angebot.status != "entwurf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Positionen können nur im Entwurf ergänzt werden"
        )

    bestehende = await positionen_fuer(session, angebot_id)
    naechste_position = max((p.position for p in bestehende), default=0) + 1
    session.add(
        AngebotPosition(
            mandant_id=angebot.mandant_id,
            angebot_id=angebot_id,
            position=naechste_position,
            beschreibung=body.beschreibung,
            menge=body.menge,
            einheit=body.einheit,
            einzelpreis=body.einzelpreis,
        )
    )
    await session.flush()
    return await to_read_model(session, angebot)


@router.patch(
    "/{angebot_id}",
    response_model=AngebotRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def update_angebot(
    angebot_id: UUID,
    body: AngebotUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AngebotRead:
    angebot = await session.get(Angebot, angebot_id)
    if angebot is None or angebot.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Angebot nicht gefunden")

    if body.gueltig_bis is not None:
        angebot.gueltig_bis = body.gueltig_bis

    if body.status is not None:
        await apply_status_transition(
            session, angebot, body.status, mandant_id=auth.mandant_id, actor_user_id=auth.user_id
        )

    await session.flush()
    await session.refresh(angebot)
    return await to_read_model(session, angebot)


@router.get("/{angebot_id}/pdf")
async def angebot_pdf(
    angebot_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    angebot = await session.get(Angebot, angebot_id)
    if angebot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Angebot nicht gefunden")
    kunde = await session.get(Kunde, angebot.kunde_id)
    positionen = await positionen_fuer(session, angebot.id)
    mandant = await session.get(Mandant, auth.mandant_id)

    pdf_bytes = generate_angebot_pdf(mandant, angebot, positionen, kunde)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{angebot.angebotsnummer}.pdf"'},
    )
