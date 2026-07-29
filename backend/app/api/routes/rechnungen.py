from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.rechnung import Rechnung, RechnungPosition
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.rechnung import RechnungCreate, RechnungPositionCreate, RechnungRead, RechnungUpdate
from app.services.numbering_service import next_rechnungsnummer
from app.services.pdf_service import generate_rechnung_pdf
from app.services.rechnung_service import positionen_fuer, to_read_model

router = APIRouter(
    prefix="/api/rechnungen",
    tags=["rechnungen"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)

_GUELTIGE_UEBERGAENGE = {
    "entwurf": {"versendet", "storniert"},
    "versendet": {"bezahlt", "storniert"},
}


@router.get("", response_model=list[RechnungRead])
async def list_rechnungen(
    kunde_id: UUID | None = Query(default=None),
    vorgang_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_db),
) -> list[RechnungRead]:
    stmt = select(Rechnung).order_by(Rechnung.created_at.desc())
    if kunde_id:
        stmt = stmt.where(Rechnung.kunde_id == kunde_id)
    if vorgang_id:
        stmt = stmt.where(Rechnung.vorgang_id == vorgang_id)
    if status_filter:
        stmt = stmt.where(Rechnung.status == status_filter)
    result = await session.execute(stmt)
    return [await to_read_model(session, r) for r in result.scalars().all()]


@router.get("/{rechnung_id}", response_model=RechnungRead)
async def get_rechnung(rechnung_id: UUID, session: AsyncSession = Depends(get_db)) -> RechnungRead:
    rechnung = await session.get(Rechnung, rechnung_id)
    if rechnung is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rechnung nicht gefunden")
    return await to_read_model(session, rechnung)


def _neue_positionen(
    rechnung_id: UUID, mandant_id: UUID, eintraege: list[RechnungPositionCreate]
) -> list[RechnungPosition]:
    return [
        RechnungPosition(
            mandant_id=mandant_id,
            rechnung_id=rechnung_id,
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
    response_model=RechnungRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_rechnung(
    body: RechnungCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RechnungRead:
    if await session.get(Kunde, body.kunde_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kunde nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    vorgang = None
    if body.vorgang_id is not None:
        vorgang = await session.get(Vorgang, body.vorgang_id)
        if vorgang is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
        if vorgang.kunde_id != body.kunde_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Vorgang gehört nicht zum angegebenen Kunden"
            )

    rechnungsnummer = await next_rechnungsnummer(session, auth.mandant_id)
    rechnung = Rechnung(
        mandant_id=auth.mandant_id,
        kunde_id=body.kunde_id,
        vorgang_id=body.vorgang_id,
        rechnungsnummer=rechnungsnummer,
        betrag_netto=body.betrag_netto,
        mwst_satz=body.mwst_satz,
        faellig_am=body.faellig_am,
        erstellt_von=auth.user_id,
    )
    session.add(rechnung)
    await session.flush()

    for p in _neue_positionen(rechnung.id, auth.mandant_id, body.positionen):
        session.add(p)
    await session.flush()
    await session.refresh(rechnung)

    if vorgang is not None:
        session.add(
            VorgangEvent(
                mandant_id=auth.mandant_id,
                vorgang_id=vorgang.id,
                event_type="rechnung_status",
                author_user_id=auth.user_id,
                body=f"Rechnung {rechnungsnummer} erstellt (Entwurf)",
                payload={"rechnung_id": str(rechnung.id), "status": "entwurf"},
            )
        )
        await session.flush()
    return await to_read_model(session, rechnung)


@router.post(
    "/{rechnung_id}/positionen",
    response_model=RechnungRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def add_position(
    rechnung_id: UUID,
    body: RechnungPositionCreate,
    session: AsyncSession = Depends(get_db),
) -> RechnungRead:
    rechnung = await session.get(Rechnung, rechnung_id)
    if rechnung is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rechnung nicht gefunden")
    if rechnung.status != "entwurf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Positionen können nur im Entwurf ergänzt werden"
        )

    bestehende = await positionen_fuer(session, rechnung_id)
    naechste_position = max((p.position for p in bestehende), default=0) + 1
    session.add(
        RechnungPosition(
            mandant_id=rechnung.mandant_id,
            rechnung_id=rechnung_id,
            position=naechste_position,
            beschreibung=body.beschreibung,
            menge=body.menge,
            einheit=body.einheit,
            einzelpreis=body.einzelpreis,
        )
    )
    await session.flush()
    await session.refresh(rechnung)
    return await to_read_model(session, rechnung)


@router.patch(
    "/{rechnung_id}",
    response_model=RechnungRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def update_rechnung(
    rechnung_id: UUID,
    body: RechnungUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RechnungRead:
    rechnung = await session.get(Rechnung, rechnung_id)
    if rechnung is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rechnung nicht gefunden")

    if body.betrag_netto is not None:
        if rechnung.status != "entwurf":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Betrag kann nur im Entwurf geändert werden"
            )
        bestehende_positionen = await positionen_fuer(session, rechnung_id)
        if bestehende_positionen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Diese Rechnung hat eigene Positionen -- der Betrag ergibt sich aus deren Summe",
            )
        rechnung.betrag_netto = body.betrag_netto
    if body.faellig_am is not None:
        rechnung.faellig_am = body.faellig_am

    neuer_status = body.status
    if neuer_status is not None:
        if neuer_status not in _GUELTIGE_UEBERGAENGE.get(rechnung.status, set()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Statuswechsel von '{rechnung.status}' nach '{neuer_status}' nicht erlaubt",
            )
        jetzt = datetime.now(timezone.utc)
        if neuer_status == "versendet":
            rechnung.versendet_am = jetzt
        elif neuer_status == "bezahlt":
            rechnung.bezahlt_am = jetzt

        rechnung.status = neuer_status

        if rechnung.vorgang_id is not None:
            vorgang = await session.get(Vorgang, rechnung.vorgang_id)
            if vorgang is not None:
                if neuer_status == "bezahlt" and vorgang.status != "abgerechnet":
                    vorgang.status = "abgerechnet"
                session.add(
                    VorgangEvent(
                        mandant_id=auth.mandant_id,
                        vorgang_id=vorgang.id,
                        event_type="rechnung_status",
                        author_user_id=auth.user_id,
                        body=f"Rechnung {rechnung.rechnungsnummer}: Status '{neuer_status}'",
                        payload={"rechnung_id": str(rechnung.id), "status": neuer_status},
                    )
                )

    await session.flush()
    await session.refresh(rechnung)
    return await to_read_model(session, rechnung)


@router.get("/{rechnung_id}/pdf")
async def rechnung_pdf(
    rechnung_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    rechnung = await session.get(Rechnung, rechnung_id)
    if rechnung is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rechnung nicht gefunden")
    kunde = await session.get(Kunde, rechnung.kunde_id)
    mandant = await session.get(Mandant, auth.mandant_id)
    positionen = await positionen_fuer(session, rechnung.id)

    pdf_bytes = generate_rechnung_pdf(mandant, rechnung, kunde, positionen)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{rechnung.rechnungsnummer}.pdf"'},
    )
