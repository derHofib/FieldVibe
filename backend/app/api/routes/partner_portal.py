from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import PartnerAuthContext, get_current_partner, get_partner_db, require_module_partner
from app.models.anlage import Anlage
from app.models.kunde import Kunde
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.partner import (
    PartnerAntwort,
    PartnerVorgangKommentar,
    PartnerVorgangRead,
    PartnerVorgangStatusUpdate,
)
from app.schemas.vorgang_event import VorgangEventRead
from app.services.event_bus import event_bus
from app.services.partner_service import apply_partner_status_transition
from app.services.vorgang_completion_service import (
    VORGANG_STATUS_GESCHLOSSEN,
    close_vorgang,
)
from app.services.vorgang_event_service import to_read_model as event_to_read_model

router = APIRouter(
    prefix="/api/partnerportal",
    tags=["partnerportal"],
    dependencies=[Depends(require_module_partner("nachunternehmer"))],
)

# Bewusst kleinere Teilmenge als der interne VORGANG_STATUS: kein
# "abgerechnet" (rein internes Abrechnungs-Feld, siehe
# vorgang_completion_service.py) und kein "storniert" (Geschaeftsentscheidung
# der Disposition, kein Ausfuehrungsstatus).
PARTNER_ERLAUBTE_STATUS = ("in_arbeit", "wartet_kunde", "abgeschlossen")


async def _require_eigener_vorgang(
    session: AsyncSession, auth: PartnerAuthContext, vorgang_id: UUID
) -> Vorgang:
    """RLS zieht fuer das Partnerportal nur die Mandanten-Grenze (siehe
    get_partner_db) -- der partner_id-Filter MUSS hier explizit passieren,
    sonst saehe ein Partner die Vorgaenge aller anderen Partner desselben
    Mandanten."""
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None or vorgang.partner_id != auth.partner_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auftrag nicht gefunden")
    return vorgang


async def _to_partner_read(session: AsyncSession, vorgang: Vorgang) -> PartnerVorgangRead:
    kunde = await session.get(Kunde, vorgang.kunde_id)
    anlage = await session.get(Anlage, vorgang.anlage_id) if vorgang.anlage_id else None
    return PartnerVorgangRead(
        id=vorgang.id,
        vorgangsnummer=vorgang.vorgangsnummer,
        titel=vorgang.titel,
        beschreibung=vorgang.beschreibung,
        leistungstyp=vorgang.leistungstyp,
        status=vorgang.status,
        partner_freigabe_status=vorgang.partner_freigabe_status,
        partner_ablehnung_grund=vorgang.partner_ablehnung_grund,
        partner_honorar_netto=vorgang.partner_honorar_netto,
        kunde_name=kunde.name if kunde else "",
        anlage_bezeichnung=anlage.bezeichnung if anlage else None,
        anlage_adresse=anlage.adresse if anlage else None,
        last_activity_at=vorgang.last_activity_at,
        created_at=vorgang.created_at,
    )


@router.get("/auftraege", response_model=list[PartnerVorgangRead])
async def list_eigene_auftraege(
    auth: PartnerAuthContext = Depends(get_current_partner),
    session: AsyncSession = Depends(get_partner_db),
) -> list[PartnerVorgangRead]:
    result = await session.execute(
        select(Vorgang)
        .where(Vorgang.partner_id == auth.partner_id)
        .order_by(Vorgang.last_activity_at.desc())
    )
    return [await _to_partner_read(session, v) for v in result.scalars().all()]


@router.get("/auftraege/{vorgang_id}", response_model=PartnerVorgangRead)
async def get_eigener_auftrag(
    vorgang_id: UUID,
    auth: PartnerAuthContext = Depends(get_current_partner),
    session: AsyncSession = Depends(get_partner_db),
) -> PartnerVorgangRead:
    vorgang = await _require_eigener_vorgang(session, auth, vorgang_id)
    return await _to_partner_read(session, vorgang)


@router.patch("/auftraege/{vorgang_id}/antwort", response_model=PartnerVorgangRead)
async def auftrag_antworten(
    vorgang_id: UUID,
    body: PartnerAntwort,
    auth: PartnerAuthContext = Depends(get_current_partner),
    session: AsyncSession = Depends(get_partner_db),
) -> PartnerVorgangRead:
    """Der Partner nimmt eine vorgeschlagene Delegation an oder lehnt sie ab
    (mit optionalem Grund) -- siehe app/services/partner_service.py fuer die
    rechtliche Begruendung, warum das kein stilles Auto-Zuweisen ist."""
    vorgang = await _require_eigener_vorgang(session, auth, vorgang_id)
    await apply_partner_status_transition(
        session,
        vorgang,
        body.status,
        mandant_id=vorgang.mandant_id,
        actor_partner_zugang_id=auth.zugang_id,
        ablehnung_grund=body.ablehnung_grund,
    )
    await session.flush()
    await session.refresh(vorgang)
    await event_bus.publish(
        vorgang.mandant_id, "feed_update", {"vorgang_id": str(vorgang.id), "reason": "geaendert"}
    )
    return await _to_partner_read(session, vorgang)


@router.patch("/auftraege/{vorgang_id}/status", response_model=PartnerVorgangRead)
async def auftrag_status_aendern(
    vorgang_id: UUID,
    body: PartnerVorgangStatusUpdate,
    auth: PartnerAuthContext = Depends(get_current_partner),
    session: AsyncSession = Depends(get_partner_db),
) -> PartnerVorgangRead:
    """Nur eine feste, bewusst kleine Teilmenge des internen Vorgang-Status
    ist ueber das Partnerportal erreichbar (PARTNER_ERLAUBTE_STATUS) --
    weder "abgerechnet" noch "storniert", dieselbe Lehre wie der im Audit
    gefundene Bug, dass der interne PATCH-Endpunkt "abgerechnet" ungeprueft
    von aussen erreichbar machte."""
    vorgang = await _require_eigener_vorgang(session, auth, vorgang_id)
    if vorgang.partner_freigabe_status != "angenommen":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Auftrag muss erst angenommen werden",
        )
    if vorgang.status in VORGANG_STATUS_GESCHLOSSEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vorgang ist abgeschlossen und kann nicht mehr geändert werden",
        )
    if body.status not in PARTNER_ERLAUBTE_STATUS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Status nicht erlaubt")

    alter_status = vorgang.status
    if body.status == "abgeschlossen":
        await close_vorgang(session, vorgang, alter_status=alter_status, author_user_id=None)
    else:
        vorgang.status = body.status
        vorgang.last_activity_at = datetime.now(timezone.utc)
        session.add(
            VorgangEvent(
                mandant_id=vorgang.mandant_id,
                vorgang_id=vorgang.id,
                event_type="status_change",
                author_user_id=None,
                payload={"von": alter_status, "nach": body.status, "partner_id": str(auth.partner_id)},
            )
        )

    await session.flush()
    await session.refresh(vorgang)
    await event_bus.publish(
        vorgang.mandant_id, "feed_update", {"vorgang_id": str(vorgang.id), "reason": "geaendert"}
    )
    return await _to_partner_read(session, vorgang)


@router.post("/auftraege/{vorgang_id}/kommentare", response_model=VorgangEventRead, status_code=status.HTTP_201_CREATED)
async def kommentar_erstellen(
    vorgang_id: UUID,
    body: PartnerVorgangKommentar,
    auth: PartnerAuthContext = Depends(get_current_partner),
    session: AsyncSession = Depends(get_partner_db),
) -> VorgangEventRead:
    vorgang = await _require_eigener_vorgang(session, auth, vorgang_id)
    if vorgang.partner_freigabe_status != "angenommen":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Auftrag muss erst angenommen werden",
        )
    if vorgang.status in VORGANG_STATUS_GESCHLOSSEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vorgang ist abgeschlossen und kann nicht mehr geändert werden",
        )

    event = VorgangEvent(
        mandant_id=vorgang.mandant_id,
        vorgang_id=vorgang.id,
        event_type="kommentar",
        author_user_id=None,
        body=body.body,
        payload={"partner_id": str(auth.partner_id), "partner_zugang_id": str(auth.zugang_id)},
    )
    session.add(event)
    vorgang.last_activity_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(event)
    await event_bus.publish(
        vorgang.mandant_id, "feed_update", {"vorgang_id": str(vorgang.id), "reason": "geaendert"}
    )
    return event_to_read_model(event)
