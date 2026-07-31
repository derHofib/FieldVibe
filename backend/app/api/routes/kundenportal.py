from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import KundenAuthContext, get_current_kunde, get_kunden_db, require_module_kunde
from app.models.angebot import Angebot
from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.rechnung import Rechnung
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.angebot import AngebotRead
from app.schemas.kundenportal import KundenAngebotAntwort
from app.schemas.rechnung import RechnungRead
from app.schemas.vorgang import VorgangRead
from app.schemas.vorgang_event import VorgangEventRead
from app.services.angebot_service import apply_status_transition, positionen_fuer, to_read_model
from app.services.pdf_service import generate_angebot_pdf, generate_rechnung_pdf
from app.services.rechnung_service import (
    positionen_fuer as rechnung_positionen_fuer,
    to_read_model as rechnung_to_read_model,
)
from app.services.vorgang_event_service import to_read_model as event_to_read_model

router = APIRouter(
    prefix="/api/kundenportal",
    tags=["kundenportal"],
    dependencies=[Depends(require_module_kunde("kundenportal"))],
)

# Nur diese beiden Uebergaenge darf der KUNDE selbst ausloesen -- "versendet"
# ist allein Sache des Betriebs (siehe app/services/angebot_service.py fuer
# die vollstaendige Uebergangstabelle, die auch hier gilt).
_KUNDE_ERLAUBTE_STATUS = ("angenommen", "abgelehnt")


async def _require_own_vorgang(session: AsyncSession, auth: KundenAuthContext, vorgang_id: UUID) -> Vorgang:
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None or vorgang.kunde_id != auth.kunde_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
    return vorgang


@router.get("/vorgaenge", response_model=list[VorgangRead])
async def list_eigene_vorgaenge(
    auth: KundenAuthContext = Depends(get_current_kunde),
    session: AsyncSession = Depends(get_kunden_db),
) -> list[Vorgang]:
    result = await session.execute(
        select(Vorgang).where(Vorgang.kunde_id == auth.kunde_id).order_by(Vorgang.last_activity_at.desc())
    )
    return list(result.scalars().all())


@router.get("/vorgaenge/{vorgang_id}", response_model=VorgangRead)
async def get_eigener_vorgang(
    vorgang_id: UUID,
    auth: KundenAuthContext = Depends(get_current_kunde),
    session: AsyncSession = Depends(get_kunden_db),
) -> Vorgang:
    return await _require_own_vorgang(session, auth, vorgang_id)


@router.get("/vorgaenge/{vorgang_id}/events", response_model=list[VorgangEventRead])
async def list_eigene_vorgang_events(
    vorgang_id: UUID,
    auth: KundenAuthContext = Depends(get_current_kunde),
    session: AsyncSession = Depends(get_kunden_db),
) -> list[VorgangEventRead]:
    await _require_own_vorgang(session, auth, vorgang_id)
    # kundensichtbar ist exakt die in Phase 2/3 dafuer eingefuehrte Trennung
    # zwischen interner und kundenfreigegebener Kommunikation -- hier hart
    # als WHERE-Bedingung erzwungen, nicht nur als UI-Filter wie im
    # internen Vorgangs-Chat (dort kann ein Mitarbeiter "Kundenansicht"
    # umschalten und sieht trotzdem alles; ein Kunde darf das nie).
    result = await session.execute(
        select(VorgangEvent)
        .where(VorgangEvent.vorgang_id == vorgang_id, VorgangEvent.kundensichtbar.is_(True))
        .order_by(VorgangEvent.id.desc())
    )
    return [event_to_read_model(e) for e in result.scalars().all()]


@router.get("/angebote", response_model=list[AngebotRead])
async def list_eigene_angebote(
    auth: KundenAuthContext = Depends(get_current_kunde),
    session: AsyncSession = Depends(get_kunden_db),
) -> list[AngebotRead]:
    result = await session.execute(
        select(Angebot).where(Angebot.kunde_id == auth.kunde_id).order_by(Angebot.created_at.desc())
    )
    return [await to_read_model(session, a) for a in result.scalars().all()]


async def _require_own_angebot(session: AsyncSession, auth: KundenAuthContext, angebot_id: UUID) -> Angebot:
    angebot = await session.get(Angebot, angebot_id)
    if angebot is None or angebot.kunde_id != auth.kunde_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Angebot nicht gefunden")
    return angebot


@router.get("/angebote/{angebot_id}", response_model=AngebotRead)
async def get_eigenes_angebot(
    angebot_id: UUID,
    auth: KundenAuthContext = Depends(get_current_kunde),
    session: AsyncSession = Depends(get_kunden_db),
) -> AngebotRead:
    angebot = await _require_own_angebot(session, auth, angebot_id)
    return await to_read_model(session, angebot)


@router.patch("/angebote/{angebot_id}", response_model=AngebotRead)
async def antwort_auf_angebot(
    angebot_id: UUID,
    body: KundenAngebotAntwort,
    auth: KundenAuthContext = Depends(get_current_kunde),
    session: AsyncSession = Depends(get_kunden_db),
) -> AngebotRead:
    if body.status not in _KUNDE_ERLAUBTE_STATUS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Als Kunde können Sie ein Angebot nur annehmen oder ablehnen",
        )
    angebot = await _require_own_angebot(session, auth, angebot_id)
    await apply_status_transition(
        session, angebot, body.status, mandant_id=auth.mandant_id, actor_user_id=None
    )
    await session.flush()
    await session.refresh(angebot)
    return await to_read_model(session, angebot)


@router.get("/angebote/{angebot_id}/pdf")
async def eigenes_angebot_pdf(
    angebot_id: UUID,
    auth: KundenAuthContext = Depends(get_current_kunde),
    session: AsyncSession = Depends(get_kunden_db),
) -> Response:
    angebot = await _require_own_angebot(session, auth, angebot_id)
    kunde = await session.get(Kunde, angebot.kunde_id)
    positionen = await positionen_fuer(session, angebot.id)
    mandant = await session.get(Mandant, auth.mandant_id)

    pdf_bytes = generate_angebot_pdf(mandant, angebot, positionen, kunde)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{angebot.angebotsnummer}.pdf"'},
    )


@router.get("/rechnungen", response_model=list[RechnungRead])
async def list_eigene_rechnungen(
    auth: KundenAuthContext = Depends(get_current_kunde),
    session: AsyncSession = Depends(get_kunden_db),
) -> list[RechnungRead]:
    result = await session.execute(
        select(Rechnung).where(Rechnung.kunde_id == auth.kunde_id).order_by(Rechnung.created_at.desc())
    )
    return [await rechnung_to_read_model(session, r) for r in result.scalars().all()]


async def _require_own_rechnung(session: AsyncSession, auth: KundenAuthContext, rechnung_id: UUID) -> Rechnung:
    rechnung = await session.get(Rechnung, rechnung_id)
    if rechnung is None or rechnung.kunde_id != auth.kunde_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rechnung nicht gefunden")
    return rechnung


@router.get("/rechnungen/{rechnung_id}", response_model=RechnungRead)
async def get_eigene_rechnung(
    rechnung_id: UUID,
    auth: KundenAuthContext = Depends(get_current_kunde),
    session: AsyncSession = Depends(get_kunden_db),
) -> RechnungRead:
    rechnung = await _require_own_rechnung(session, auth, rechnung_id)
    return await rechnung_to_read_model(session, rechnung)


@router.get("/rechnungen/{rechnung_id}/pdf")
async def eigene_rechnung_pdf(
    rechnung_id: UUID,
    auth: KundenAuthContext = Depends(get_current_kunde),
    session: AsyncSession = Depends(get_kunden_db),
) -> Response:
    rechnung = await _require_own_rechnung(session, auth, rechnung_id)
    kunde = await session.get(Kunde, rechnung.kunde_id)
    mandant = await session.get(Mandant, auth.mandant_id)
    positionen = await rechnung_positionen_fuer(session, rechnung.id)

    pdf_bytes = generate_rechnung_pdf(mandant, rechnung, kunde, positionen)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{rechnung.rechnungsnummer}.pdf"'},
    )
