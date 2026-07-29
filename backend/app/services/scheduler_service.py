from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import system_session
from app.models.anlage import Anlage
from app.models.audit_log import AuditLog
from app.models.notification import Notification
from app.models.pruefmittel import Pruefmittel
from app.models.pruefzyklus import Pruefzyklus
from app.models.user import User
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.services.event_bus import event_bus
from app.services.numbering_service import next_vorgangsnummer

SCHEDULER_AKTION = "pruefzyklen_scheduler_run"


async def _admins_und_disponenten(session: AsyncSession, mandant_id) -> list[User]:
    result = await session.execute(
        select(User).where(
            User.mandant_id == mandant_id,
            User.role.in_(("mandant_admin", "disponent")),
            User.aktiv.is_(True),
        )
    )
    return list(result.scalars().all())


async def _hat_offene_notification(session: AsyncSession, *, user_id, ref_entity_id) -> bool:
    result = await session.execute(
        select(Notification.id)
        .where(
            Notification.user_id == user_id,
            Notification.ref_entity_type == "pruefmittel",
            Notification.ref_entity_id == ref_entity_id,
            Notification.gelesen_am.is_(None),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def run_pruefzyklen_scheduler() -> dict:
    """Taeglicher Lauf (Abschnitt 12): legt fuer faellige Pruefzyklen einen
    Vorgang an und benachrichtigt Admin/Disponent -- pro Zyklus nur einmal,
    bis die zugehoerige Pruefung tatsaechlich durchgefuehrt wurde (siehe
    Pruefzyklus.offener_vorgang_id, der beim Abschluss des Vorgangs wieder
    geleert wird, app/api/routes/vorgaenge.py). Faellige Pruefmittel
    erzeugen keinen Vorgang (Kalibrierung ist kein Kundenauftrag), nur eine
    wiederkehrende Erinnerung, solange keine ungelesene dazu offen ist."""
    settings = get_settings()
    heute = date.today()
    horizont = heute + timedelta(days=settings.pruefzyklus_vorlauf_tage)

    erstellte_vorgaenge = 0
    faellige_pruefmittel = 0

    async with system_session() as session:
        pruefzyklen = (
            await session.execute(
                select(Pruefzyklus).where(
                    Pruefzyklus.aktiv.is_(True),
                    Pruefzyklus.naechste_pruefung_am <= horizont,
                    Pruefzyklus.offener_vorgang_id.is_(None),
                )
            )
        ).scalars().all()

        for zyklus in pruefzyklen:
            anlage = await session.get(Anlage, zyklus.anlage_id)
            if anlage is None:
                continue

            vorgangsnummer = await next_vorgangsnummer(session, zyklus.mandant_id)
            vorgang = Vorgang(
                mandant_id=zyklus.mandant_id,
                vorgangsnummer=vorgangsnummer,
                kunde_id=anlage.kunde_id,
                anlage_id=anlage.id,
                titel=f"Wiederkehrende Prüfung: {zyklus.bezeichnung}",
                beschreibung=(
                    "Automatisch vom Prüfzyklen-Scheduler angelegt (fällig "
                    f"{zyklus.naechste_pruefung_am.isoformat()})."
                ),
                abrechnungsart="wartungsvertrag",
                leistungstyp="pruefung",
            )
            session.add(vorgang)
            await session.flush()

            zyklus.offener_vorgang_id = vorgang.id

            session.add(
                VorgangEvent(
                    mandant_id=zyklus.mandant_id,
                    vorgang_id=vorgang.id,
                    event_type="system",
                    is_system=True,
                    body="Automatisch angelegt durch den Prüfzyklen-Scheduler",
                    payload={"pruefzyklus_id": str(zyklus.id)},
                )
            )

            for empfaenger in await _admins_und_disponenten(session, zyklus.mandant_id):
                session.add(
                    Notification(
                        mandant_id=zyklus.mandant_id,
                        user_id=empfaenger.id,
                        typ="frist",
                        titel=f"Prüfung fällig: {zyklus.bezeichnung} ({anlage.bezeichnung})",
                        ref_entity_type="vorgang",
                        ref_entity_id=vorgang.id,
                    )
                )
            await session.flush()

            await event_bus.publish(
                zyklus.mandant_id,
                "feed_update",
                {"vorgang_id": str(vorgang.id), "reason": "erstellt"},
            )
            erstellte_vorgaenge += 1

        pruefmittel_faellig = (
            await session.execute(
                select(Pruefmittel).where(
                    Pruefmittel.status == "aktiv",
                    Pruefmittel.naechste_kalibrierung_am <= horizont,
                )
            )
        ).scalars().all()

        for mittel in pruefmittel_faellig:
            empfaenger_liste = list(await _admins_und_disponenten(session, mittel.mandant_id))
            if mittel.zugewiesen_an is not None:
                zugewiesener = await session.get(User, mittel.zugewiesen_an)
                if zugewiesener is not None and all(
                    zugewiesener.id != e.id for e in empfaenger_liste
                ):
                    empfaenger_liste.append(zugewiesener)

            for empfaenger in empfaenger_liste:
                if await _hat_offene_notification(
                    session, user_id=empfaenger.id, ref_entity_id=mittel.id
                ):
                    continue
                session.add(
                    Notification(
                        mandant_id=mittel.mandant_id,
                        user_id=empfaenger.id,
                        typ="frist",
                        titel=f"Kalibrierung fällig: {mittel.bezeichnung}",
                        ref_entity_type="pruefmittel",
                        ref_entity_id=mittel.id,
                    )
                )
            faellige_pruefmittel += 1

        ergebnis = {
            "vorgaenge_erstellt": erstellte_vorgaenge,
            "pruefmittel_faellig": faellige_pruefmittel,
        }
        session.add(
            AuditLog(
                mandant_id=None,
                actor_user_id=None,
                aktion=SCHEDULER_AKTION,
                entity_type="scheduler",
                payload=ergebnis,
            )
        )
        await session.flush()

    return ergebnis


async def get_last_scheduler_run() -> datetime | None:
    async with system_session() as session:
        result = await session.execute(
            select(AuditLog.created_at)
            .where(AuditLog.aktion == SCHEDULER_AKTION)
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
