from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import PartnerAuthContext, get_current_partner, get_partner_db, require_module_partner
from app.models.anlage import Anlage
from app.models.kunde import Kunde
from app.models.notification import Notification
from app.models.partner import Partner
from app.models.projekt import Projekt, ProjektAufgabe
from app.models.vorgang import Vorgang
from app.models.user import User
from app.models.vorgang_event import VorgangEvent
from app.schemas.partner import (
    PartnerAntwort,
    PartnerKommentarRead,
    PartnerVorgangKommentar,
    PartnerVorgangRead,
    PartnerVorgangStatusUpdate,
    PartnerZeitplanSchritt,
)
from app.schemas.vorgang_event import VorgangEventRead
from app.services.event_bus import event_bus
from app.services.zuweisung_service import dispo_verantwortliche_user_ids
from app.services.partner_service import apply_partner_status_transition
from app.services.zeitplan_service import VORGANG_ERLEDIGT
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
    if vorgang is None or vorgang.partner_id != auth.partner_id or vorgang.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
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


@router.get("/zeitplan", response_model=list[PartnerZeitplanSchritt])
async def list_eigene_zeitplan_schritte(
    auth: PartnerAuthContext = Depends(get_current_partner),
    session: AsyncSession = Depends(get_partner_db),
) -> list[PartnerZeitplanSchritt]:
    """Read-only: die dem Partner zugeordneten Fremdgewerk-Schritte aus den
    Projekt-Zeitplaenen. Der partner_id-Filter ist hier die eigentliche
    Zugriffsgrenze (RLS zieht nur den Mandanten), und das Schema gibt
    bewusst nichts ausser Titel/Projektname/Zeitraum/Stand heraus."""
    phase = aliased(ProjektAufgabe)
    grenze = datetime.now(timezone.utc).date() - timedelta(days=30)
    zeilen = (
        await session.execute(
            select(
                ProjektAufgabe.id,
                ProjektAufgabe.titel,
                Projekt.name,
                phase.titel,
                ProjektAufgabe.start_am,
                ProjektAufgabe.ende_am,
                ProjektAufgabe.fortschritt,
                ProjektAufgabe.erledigt_am,
                ProjektAufgabe.vorgang_id,
                Vorgang.status,
            )
            .join(Projekt, Projekt.id == ProjektAufgabe.projekt_id)
            .outerjoin(
                phase, (phase.id == ProjektAufgabe.plan_phase_id) & (phase.geloescht_am.is_(None))
            )
            .outerjoin(
                Vorgang, (Vorgang.id == ProjektAufgabe.vorgang_id) & (Vorgang.geloescht_am.is_(None))
            )
            .where(
                ProjektAufgabe.partner_id == auth.partner_id,
                ProjektAufgabe.typ == "schritt",
                ProjektAufgabe.geloescht_am.is_(None),
                Projekt.geloescht_am.is_(None),
                Projekt.archiviert.is_(False),
                (ProjektAufgabe.ende_am.is_(None)) | (ProjektAufgabe.ende_am >= grenze),
            )
            .order_by(ProjektAufgabe.start_am.asc().nulls_last(), ProjektAufgabe.created_at)
        )
    ).all()
    ergebnis = []
    for r in zeilen:
        erledigt = r[9] in VORGANG_ERLEDIGT if r[9] is not None else r[7] is not None
        ergebnis.append(
            PartnerZeitplanSchritt(
                id=r[0],
                titel=r[1],
                projekt_name=r[2],
                phase_titel=r[3],
                start_am=r[4],
                ende_am=r[5],
                fortschritt=100 if r[8] is not None and erledigt else r[6],
                erledigt=erledigt,
            )
        )
    return ergebnis


@router.get("/auftraege", response_model=list[PartnerVorgangRead])
async def list_eigene_auftraege(
    auth: PartnerAuthContext = Depends(get_current_partner),
    session: AsyncSession = Depends(get_partner_db),
) -> list[PartnerVorgangRead]:
    result = await session.execute(
        select(Vorgang)
        .where(Vorgang.partner_id == auth.partner_id, Vorgang.geloescht_am.is_(None))
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
            detail="Vorgang muss erst angenommen werden",
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


@router.get("/auftraege/{vorgang_id}/kommentare", response_model=list[PartnerKommentarRead])
async def list_kommentare(
    vorgang_id: UUID,
    auth: PartnerAuthContext = Depends(get_current_partner),
    session: AsyncSession = Depends(get_partner_db),
) -> list[PartnerKommentarRead]:
    """Nur eigene Partner-Kommentare und im Office ausdruecklich freigegebene
    (partner_sichtbar) -- alles andere im Verlauf ist intern. Bewusst kein
    VorgangEventRead: autor_name statt User-ID, keine Payloads."""
    vorgang = await _require_eigener_vorgang(session, auth, vorgang_id)
    zeilen = (
        await session.execute(
            select(VorgangEvent, User.name)
            .outerjoin(User, User.id == VorgangEvent.author_user_id)
            .where(
                VorgangEvent.vorgang_id == vorgang.id,
                VorgangEvent.event_type == "kommentar",
                VorgangEvent.partner_sichtbar.is_(True),
                VorgangEvent.body.is_not(None),
                # Kommentare eines frueher zugewiesenen anderen Partners
                # bleiben ausgeblendet.
                (VorgangEvent.author_user_id.is_not(None))
                | (VorgangEvent.payload["partner_id"].astext == str(auth.partner_id)),
            )
            .order_by(VorgangEvent.id.asc())
        )
    ).all()
    return [
        PartnerKommentarRead(
            id=e.id,
            text=e.body or "",
            erstellt_am=e.created_at,
            autor="betrieb" if e.author_user_id is not None else "partner",
            autor_name=(user_name or "Ihr Ansprechpartner")
            if e.author_user_id is not None
            else "Sie",
        )
        for e, user_name in zeilen
    ]


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
            detail="Vorgang muss erst angenommen werden",
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
        partner_sichtbar=True,
        payload={"partner_id": str(auth.partner_id), "partner_zugang_id": str(auth.zugang_id)},
    )
    session.add(event)
    vorgang.last_activity_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(event)

    empfaenger = (
        {vorgang.zugewiesener_user_id}
        if vorgang.zugewiesener_user_id is not None
        else await dispo_verantwortliche_user_ids(session, vorgang.mandant_id)
    )
    partner = await session.get(Partner, auth.partner_id)
    for user_id in empfaenger:
        session.add(
            Notification(
                mandant_id=vorgang.mandant_id,
                user_id=user_id,
                typ="partner_kommentar",
                titel=(
                    f"Neuer Kommentar von {partner.name if partner else 'Partner'} "
                    f"zu {vorgang.vorgangsnummer}: {vorgang.titel}"
                ),
                ref_entity_type="vorgang",
                ref_entity_id=vorgang.id,
            )
        )
    await session.flush()
    await event_bus.publish(
        vorgang.mandant_id, "feed_update", {"vorgang_id": str(vorgang.id), "reason": "geaendert"}
    )
    return event_to_read_model(event)
