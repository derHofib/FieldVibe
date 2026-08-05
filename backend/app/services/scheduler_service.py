from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import system_session
from app.models.anlage import Anlage
from app.models.audit_log import AuditLog
from app.models.dauerauftrag import Dauerauftrag
from app.models.dauerauftrag_ziel import DauerauftragZiel
from app.models.inventurzyklus import InventurZyklus
from app.models.mandant import Mandant
from app.models.notification import Notification
from app.models.pruefmittel import Pruefmittel
from app.models.pruefzyklus import Pruefzyklus
from app.models.user import User
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.services.event_bus import event_bus
from app.services.fahrzeug_zuweisung_service import technikern_zugewiesen
from app.services.numbering_service import next_vorgangsnummer
from app.services.zuweisung_service import dispo_verantwortliche_user_ids

SCHEDULER_AKTION = "pruefzyklen_scheduler_run"
DAUERAUFTRAEGE_SCHEDULER_AKTION = "dauerauftraege_scheduler_run"


async def mandanten_faellig_um(session: AsyncSession, stunde_utc: int) -> list[UUID]:
    """Welche aktiven Mandanten haben genau jetzt (`stunde_utc`, 0-23) ihre
    taegliche Scheduler-Stunde erreicht? NULL (kein eigener Wert gesetzt)
    faellt auf den globalen Default zurueck (siehe Mandant.scheduler_stunde_utc
    und Settings.scheduler_default_stunde_utc)."""
    settings = get_settings()
    result = await session.execute(
        select(Mandant.id, Mandant.scheduler_stunde_utc).where(Mandant.status == "aktiv")
    )
    return [
        mandant_id
        for mandant_id, konfigurierte_stunde in result.all()
        if (konfigurierte_stunde if konfigurierte_stunde is not None else settings.scheduler_default_stunde_utc)
        == stunde_utc
    ]


async def _admins_und_disponenten(session: AsyncSession, mandant_id) -> list[User]:
    user_ids = await dispo_verantwortliche_user_ids(session, mandant_id)
    if not user_ids:
        return []
    result = await session.execute(select(User).where(User.id.in_(user_ids)))
    return list(result.scalars().all())


async def _hat_offene_notification(session: AsyncSession, *, user_id, ref_entity_type, ref_entity_id) -> bool:
    result = await session.execute(
        select(Notification.id)
        .where(
            Notification.user_id == user_id,
            Notification.ref_entity_type == ref_entity_type,
            Notification.ref_entity_id == ref_entity_id,
            Notification.gelesen_am.is_(None),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def run_pruefzyklen_scheduler(mandant_ids: list[UUID] | None = None) -> dict:
    """Taeglicher Lauf (Abschnitt 12): legt fuer faellige Pruefzyklen einen
    Vorgang an und benachrichtigt Admin/Disponent -- pro Zyklus nur einmal,
    bis die zugehoerige Pruefung tatsaechlich durchgefuehrt wurde (siehe
    Pruefzyklus.offener_vorgang_id, der beim Abschluss des Vorgangs wieder
    geleert wird, app/api/routes/vorgaenge.py). Faellige Pruefmittel und
    Inventurzyklen erzeugen keinen Vorgang (Kalibrierung/Inventur sind kein
    Kundenauftrag), nur eine wiederkehrende Erinnerung, solange keine
    ungelesene dazu offen ist.

    `mandant_ids` grenzt den Lauf auf die Mandanten ein, deren konfigurierte
    Scheduler-Stunde gerade erreicht ist (siehe app/worker.py) -- None (z.B.
    aus Tests oder einem manuellen Voll-Lauf) bearbeitet weiterhin alle
    Mandanten."""
    settings = get_settings()
    heute = date.today()
    horizont = heute + timedelta(days=settings.pruefzyklus_vorlauf_tage)

    erstellte_vorgaenge = 0
    faellige_pruefmittel = 0
    faellige_inventurzyklen = 0

    async with system_session() as session:
        pruefzyklen_stmt = select(Pruefzyklus).where(
            Pruefzyklus.aktiv.is_(True),
            Pruefzyklus.naechste_pruefung_am <= horizont,
            Pruefzyklus.offener_vorgang_id.is_(None),
        )
        if mandant_ids is not None:
            pruefzyklen_stmt = pruefzyklen_stmt.where(Pruefzyklus.mandant_id.in_(mandant_ids))
        pruefzyklen = (await session.execute(pruefzyklen_stmt)).scalars().all()

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

        pruefmittel_stmt = select(Pruefmittel).where(
            Pruefmittel.status == "aktiv",
            Pruefmittel.naechste_kalibrierung_am <= horizont,
        )
        if mandant_ids is not None:
            pruefmittel_stmt = pruefmittel_stmt.where(Pruefmittel.mandant_id.in_(mandant_ids))
        pruefmittel_faellig = (await session.execute(pruefmittel_stmt)).scalars().all()

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
                    session, user_id=empfaenger.id, ref_entity_type="pruefmittel", ref_entity_id=mittel.id
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

        # Faellige Inventurzyklen (aktiv, siehe app/models/inventurzyklus.py)
        # erzeugen -- wie Pruefmittel -- keinen Vorgang, nur eine
        # wiederkehrende Erinnerung: eine Inventur ist ein interner Vorgang
        # am Lagerort, kein Kundenauftrag. Ist der Lagerort ein Fahrzeug,
        # wird zusaetzlich der/die zugewiesene(n) Techniker benachrichtigt
        # (siehe app/services/fahrzeug_zuweisung_service.py) -- die
        # tatsaechlichen Nutzer des Lagerorts sollen es genauso mitbekommen
        # wie Admin/Disponent.
        inventurzyklen_stmt = select(InventurZyklus).where(
            InventurZyklus.aktiv.is_(True),
            InventurZyklus.naechste_inventur_am <= horizont,
        )
        if mandant_ids is not None:
            inventurzyklen_stmt = inventurzyklen_stmt.where(InventurZyklus.mandant_id.in_(mandant_ids))
        inventurzyklen_faellig = (await session.execute(inventurzyklen_stmt)).scalars().all()

        for zyklus in inventurzyklen_faellig:
            lager = await session.get(Anlage, zyklus.lager_id)
            if lager is None:
                continue

            empfaenger_liste = list(await _admins_und_disponenten(session, zyklus.mandant_id))
            if lager.objekttyp == "fahrzeug":
                for techniker in await technikern_zugewiesen(session, lager.id):
                    if all(techniker.id != e.id for e in empfaenger_liste):
                        empfaenger_liste.append(techniker)

            for empfaenger in empfaenger_liste:
                if await _hat_offene_notification(
                    session, user_id=empfaenger.id, ref_entity_type="anlage", ref_entity_id=lager.id
                ):
                    continue
                session.add(
                    Notification(
                        mandant_id=zyklus.mandant_id,
                        user_id=empfaenger.id,
                        typ="frist",
                        titel=f"Inventur fällig: {lager.bezeichnung}",
                        ref_entity_type="anlage",
                        ref_entity_id=lager.id,
                    )
                )
            faellige_inventurzyklen += 1

        ergebnis = {
            "vorgaenge_erstellt": erstellte_vorgaenge,
            "pruefmittel_faellig": faellige_pruefmittel,
            "inventurzyklen_faellig": faellige_inventurzyklen,
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


async def run_dauerauftraege_scheduler(mandant_ids: list[UUID] | None = None) -> dict:
    """Stuendlicher Lauf: legt fuer faellige Ziele eines Dauerauftrags
    (wiederkehrender Auftrag, siehe app/models/dauerauftrag.py, gebuendelt
    ueber app/models/dauerauftrag_ziel.py) je einen neuen Vorgang an -- pro
    Ziel nur einen gleichzeitig offenen (offener_vorgang_id), bis der
    zuletzt erzeugte Vorgang abgeschlossen wird (siehe
    app/api/routes/vorgaenge.py, der die naechste Faelligkeit dann relativ
    zum tatsaechlichen Abschlussdatum fortschreibt). Ein Buendel mit
    mehreren Zielen (z.B. mehreren Anlagen desselben Kunden) laeuft dadurch
    je Ziel unabhaengig -- ein liegen gebliebenes Ziel blockiert nicht die
    anderen. Anders als bei Pruefzyklen kein Vorlauf-Horizont -- die
    Erzeugung erfolgt erst, wenn naechste_faelligkeit_am tatsaechlich
    erreicht ist.

    `mandant_ids` grenzt den Lauf wie beim Pruefzyklen-Scheduler auf die
    gerade faelligen Mandanten ein (siehe app/worker.py); None bearbeitet
    alle Mandanten."""
    heute = date.today()
    erstellte_vorgaenge = 0

    async with system_session() as session:
        stmt = (
            select(DauerauftragZiel, Dauerauftrag)
            .join(Dauerauftrag, DauerauftragZiel.dauerauftrag_id == Dauerauftrag.id)
            .where(
                Dauerauftrag.aktiv.is_(True),
                DauerauftragZiel.naechste_faelligkeit_am <= heute,
                DauerauftragZiel.offener_vorgang_id.is_(None),
            )
        )
        if mandant_ids is not None:
            stmt = stmt.where(Dauerauftrag.mandant_id.in_(mandant_ids))
        faellige_ziele = (await session.execute(stmt)).all()

        for ziel, auftrag in faellige_ziele:
            vorgangsnummer = await next_vorgangsnummer(session, auftrag.mandant_id)
            # Wunsch-Enddatum = geplante Faelligkeit plus Gleitzeit nach hinten
            # (toleranz_spaet_tage) -- der Vorgang gilt im Feed erst als
            # ueberfaellig, wenn die Gleitzeit tatsaechlich ausgeschoepft ist,
            # analog zur Hinweis-statt-Blockade-Logik beim Abschluss (siehe
            # vorgang_completion_service.py).
            faelligkeit_am = datetime.combine(
                ziel.naechste_faelligkeit_am + timedelta(days=auftrag.toleranz_spaet_tage or 0),
                time.min,
                tzinfo=timezone.utc,
            )
            vorgang = Vorgang(
                mandant_id=auftrag.mandant_id,
                vorgangsnummer=vorgangsnummer,
                kunde_id=auftrag.kunde_id,
                anlage_id=ziel.anlage_id,
                dauerauftrag_id=auftrag.id,
                titel=auftrag.titel,
                beschreibung=auftrag.beschreibung,
                abrechnungsart=auftrag.abrechnungsart,
                leistungstyp=auftrag.leistungstyp,
                faelligkeit_am=faelligkeit_am,
            )
            session.add(vorgang)
            await session.flush()

            ziel.offener_vorgang_id = vorgang.id

            session.add(
                VorgangEvent(
                    mandant_id=auftrag.mandant_id,
                    vorgang_id=vorgang.id,
                    event_type="system",
                    is_system=True,
                    body="Automatisch angelegt durch den Dauerauftrag-Scheduler",
                    payload={"dauerauftrag_id": str(auftrag.id), "dauerauftrag_ziel_id": str(ziel.id)},
                )
            )

            for empfaenger in await _admins_und_disponenten(session, auftrag.mandant_id):
                session.add(
                    Notification(
                        mandant_id=auftrag.mandant_id,
                        user_id=empfaenger.id,
                        typ="frist",
                        titel=f"Dauerauftrag fällig: {auftrag.titel}",
                        ref_entity_type="vorgang",
                        ref_entity_id=vorgang.id,
                    )
                )
            await session.flush()

            await event_bus.publish(
                auftrag.mandant_id,
                "feed_update",
                {"vorgang_id": str(vorgang.id), "reason": "erstellt"},
            )
            erstellte_vorgaenge += 1

        ergebnis = {"vorgaenge_erstellt": erstellte_vorgaenge}
        session.add(
            AuditLog(
                mandant_id=None,
                actor_user_id=None,
                aktion=DAUERAUFTRAEGE_SCHEDULER_AKTION,
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
