"""Mail-Outbox: zuverlaessiger Versand mit Retry.

Ablauf: Die ausloesende Aktion legt in IHRER Transaktion eine Outbox-Zeile (plus
EmailLog "ausstehend") an -- rollt sie zurueck, gibt es keine Mail. Nach dem Commit
holt der Worker faellige Zeilen ab (FOR UPDATE SKIP LOCKED, Status pending -> sending
in einer eigenen kurzen Transaktion), versendet OHNE offene Sperre und schreibt das
Ergebnis in einer zweiten Transaktion zurueck.

Kein Doppelversand: Stuerzt der Worker zwischen SMTP-Erfolg und Rueckschreiben ab,
bleibt die Zeile in "sending". Sie wird nach mail_outbox_sending_timeout_minuten NICHT
erneut gesendet, sondern auf "failed" gesetzt (Zustellung unbekannt) und gemeldet --
lieber eine Mail von Hand pruefen als einem Kunden zwei Mahnungen schicken.
"""
import logging
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging_config import schwaerze
from app.core.zeit import in_lokal
from app.db.session import system_session
from app.models.email_log import EmailLog
from app.models.mail_outbox import MailOutbox
from app.models.notification import Notification
from app.services import email_service, storage_service
from app.services.event_bus import event_bus
from app.services.zuweisung_service import dispo_verantwortliche_user_ids

logger = logging.getLogger("app.mail_outbox")

Anhang = tuple[str, bytes, str]
_MAX_FEHLER_ZEICHEN = 500


def backoff_plan() -> list[int]:
    return [int(t) for t in get_settings().mail_outbox_backoff_minuten.split(",") if t.strip()]


def naechster_versuch(versuche: int, jetzt: datetime) -> datetime | None:
    """`versuche` = Zahl der bisher gescheiterten Versuche (>= 1). None = Plan erschoepft."""
    plan = backoff_plan()
    if versuche < 1 or versuche > len(plan):
        return None
    return jetzt + timedelta(minutes=plan[versuche - 1])


# --- Einreihen (in der Transaktion der ausloesenden Aktion) ------------------------


async def enqueue_email(
    session: AsyncSession,
    mandant_id: UUID | None,
    *,
    to: str,
    subject: str,
    body: str,
    html_body: str | None = None,
    erstellt_von: UUID | None = None,
    attachment: Anhang | None = None,
    weitere_anhaenge: list[Anhang] | None = None,
    email_log: EmailLog | None = None,
) -> MailOutbox:
    outbox_id = uuid4()
    anhaenge: list[dict] = []
    alle = [*([attachment] if attachment is not None else []), *(weitere_anhaenge or [])]
    for index, (dateiname, inhalt, mimetype) in enumerate(alle):
        key = storage_service.new_mail_outbox_key(mandant_id, outbox_id, index)
        # Vor dem Commit hochgeladen: scheitert die Transaktion danach, bleibt hoechstens ein
        # verwaistes Objekt unter mail-outbox/ liegen (siehe docs/BETRIEB.md), nie eine Mail ohne Anhang.
        await storage_service.upload_bytes(key, inhalt, mimetype)
        anhaenge.append({"dateiname": dateiname, "mimetype": mimetype, "s3_key": key})

    outbox = MailOutbox(
        id=outbox_id,
        mandant_id=mandant_id,
        email_log_id=email_log.id if email_log is not None else None,
        erstellt_von=erstellt_von,
        empfaenger=to,
        betreff=subject,
        body=body,
        html_body=html_body,
        anhaenge=anhaenge,
    )
    session.add(outbox)
    await session.flush()
    return outbox


async def enqueue_email_and_log(
    session: AsyncSession,
    mandant_id: UUID,
    *,
    entity_type: str,
    entity_id: UUID,
    to: str,
    subject: str,
    body: str,
    gesendet_von: UUID | None = None,
    attachment: Anhang | None = None,
    weitere_anhaenge: list[Anhang] | None = None,
) -> EmailLog:
    """Gegenstueck zu email_service.send_email_and_log fuer Aufrufer ohne Bedarf an einem
    synchronen Ergebnis: der Verlaufseintrag steht sofort da (Status "ausstehend") und wird
    vom Worker auf "gesendet" bzw. "fehler" nachgezogen."""
    log = EmailLog(
        mandant_id=mandant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        empfaenger=to,
        betreff=subject,
        inhalt=body,
        anhang_dateiname=attachment[0] if attachment else None,
        status="ausstehend",
        gesendet_von=gesendet_von,
    )
    session.add(log)
    await session.flush()
    await enqueue_email(
        session, mandant_id, to=to, subject=subject, body=body, erstellt_von=gesendet_von,
        attachment=attachment, weitere_anhaenge=weitere_anhaenge, email_log=log,
    )
    await session.refresh(log)
    return log


# --- Abarbeiten (Worker, nach dem Commit der ausloesenden Transaktion) -------------


@dataclass
class _Auftrag:
    id: UUID
    mandant_id: UUID | None
    empfaenger: str
    betreff: str
    body: str
    html_body: str | None
    anhaenge: list[dict]


def _ist_dauerhaft(exc: Exception) -> bool:
    """Fehler, bei denen ein Wiederholen nichts aendert."""
    if isinstance(exc, email_service.EmailNichtKonfiguriert):
        return True
    if isinstance(exc, (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused)):
        return True
    if isinstance(exc, smtplib.SMTPResponseException) and 500 <= exc.smtp_code < 600:
        return not isinstance(exc, smtplib.SMTPAuthenticationError)
    if isinstance(exc, ClientError) and exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
        return True
    return False


def _fehlertext(exc: Exception) -> str:
    if isinstance(exc, email_service.EmailNichtKonfiguriert):
        return "Kein SMTP-Postfach für diesen Mandanten hinterlegt (siehe Integrationen)."
    return schwaerze(str(exc) or type(exc).__name__)[:_MAX_FEHLER_ZEICHEN]


async def _beanspruche(max_anzahl: int, jetzt: datetime) -> list[_Auftrag]:
    async with system_session() as session:
        zeilen = (await session.execute(
            select(MailOutbox)
            .where(MailOutbox.status == "pending", MailOutbox.naechster_versuch_am <= jetzt)
            .order_by(MailOutbox.naechster_versuch_am)
            .limit(max_anzahl)
            .with_for_update(skip_locked=True)
        )).scalars().all()
        auftraege = []
        for z in zeilen:
            z.status = "sending"
            z.versuche += 1
            z.sending_seit = jetzt
            auftraege.append(_Auftrag(z.id, z.mandant_id, z.empfaenger, z.betreff, z.body, z.html_body, list(z.anhaenge)))
    return auftraege


async def _benachrichtige_fehlschlag(session: AsyncSession, row: MailOutbox, log: EmailLog | None, grund: str) -> None:
    logger.error(
        "Mail an %s endgueltig fehlgeschlagen: %s", row.empfaenger, grund,
        extra={"event": "mail_outbox_failed"},
    )
    if row.mandant_id is None:
        return
    empfaenger = {row.erstellt_von} if row.erstellt_von else set(await dispo_verantwortliche_user_ids(session, row.mandant_id))
    for user_id in empfaenger:
        session.add(Notification(
            mandant_id=row.mandant_id,
            user_id=user_id,
            typ="frist",
            titel=f"E-Mail nicht zugestellt: „{row.betreff[:80]}“ an {row.empfaenger}",
            ref_entity_type=log.entity_type if log else None,
            ref_entity_id=log.entity_id if log else None,
        ))
        await event_bus.publish(row.mandant_id, "notification", {"typ": "frist", "user_id": str(user_id)})


async def _endgueltig_fehlgeschlagen(session: AsyncSession, row: MailOutbox, log: EmailLog | None, grund: str) -> None:
    row.status = "failed"
    row.sending_seit = None
    row.letzter_fehler = grund
    if log is not None:
        log.status = "fehler"
        log.fehlermeldung = grund
    await _benachrichtige_fehlschlag(session, row, log, grund)


async def _bereinige_haengende(jetzt: datetime) -> int:
    grenze = jetzt - timedelta(minutes=get_settings().mail_outbox_sending_timeout_minuten)
    async with system_session() as session:
        zeilen = (await session.execute(
            select(MailOutbox)
            .where(MailOutbox.status == "sending", MailOutbox.sending_seit < grenze)
            .with_for_update(skip_locked=True)
        )).scalars().all()
        for row in zeilen:
            log = await session.get(EmailLog, row.email_log_id) if row.email_log_id else None
            await _endgueltig_fehlgeschlagen(
                session, row, log,
                "Worker-Abbruch während des Versands: Zustellung unbekannt, nicht automatisch wiederholt "
                "(sonst droht ein Doppelversand). Bitte prüfen und bei Bedarf erneut senden.",
            )
        return len(zeilen)


async def _schreibe_ergebnis(auftrag: _Auftrag, jetzt: datetime, exc: Exception | None, stats: dict) -> None:
    geloeschte_keys: list[str] = []
    async with system_session() as session:
        row = (await session.execute(
            select(MailOutbox).where(MailOutbox.id == auftrag.id).with_for_update()
        )).scalar_one()
        log = await session.get(EmailLog, row.email_log_id) if row.email_log_id else None
        if exc is None:
            row.status = "sent"
            row.gesendet_am = jetzt
            row.sending_seit = None
            row.letzter_fehler = None
            if log is not None:
                log.status = "gesendet"
                log.fehlermeldung = None
            geloeschte_keys = [a["s3_key"] for a in row.anhaenge]
            stats["gesendet"] += 1
        else:
            fehler = _fehlertext(exc)
            naechster = None if _ist_dauerhaft(exc) else naechster_versuch(row.versuche, jetzt)
            if naechster is None:
                await _endgueltig_fehlgeschlagen(session, row, log, fehler)
                stats["fehlgeschlagen"] += 1
            else:
                row.status = "pending"
                row.sending_seit = None
                row.letzter_fehler = fehler
                row.naechster_versuch_am = naechster
                if log is not None:
                    log.fehlermeldung = (
                        f"Versuch {row.versuche} fehlgeschlagen ({fehler}); "
                        f"nächster Versuch {in_lokal(naechster).strftime('%d.%m. %H:%M')} Uhr"
                    )
                logger.warning(
                    "Mail-Versand an %s fehlgeschlagen (Versuch %d), neuer Versuch %s: %s",
                    row.empfaenger, row.versuche, naechster.isoformat(), fehler,
                )
                stats["wiederholt"] += 1
    # Erst nach dem Commit: scheitert das Aufraeumen, ist die Mail trotzdem als gesendet vermerkt.
    for key in geloeschte_keys:
        try:
            await storage_service.delete_object(key)
        except Exception:
            logger.warning("Anhang %s der Outbox-Mail konnte nicht geloescht werden", key)


async def _versende(auftrag: _Auftrag, jetzt: datetime, stats: dict) -> None:
    try:
        anhaenge: list[Anhang] = [
            (a["dateiname"], await storage_service.download_bytes(a["s3_key"]), a["mimetype"])
            for a in auftrag.anhaenge
        ]
        async with system_session() as session:
            await email_service.send_email(
                session,
                auftrag.mandant_id,
                to=auftrag.empfaenger,
                subject=auftrag.betreff,
                body=auftrag.body,
                html_body=auftrag.html_body,
                attachment=anhaenge[0] if anhaenge else None,
                weitere_anhaenge=anhaenge[1:] or None,
            )
    except Exception as exc:
        await _schreibe_ergebnis(auftrag, jetzt, exc, stats)
    else:
        await _schreibe_ergebnis(auftrag, jetzt, None, stats)


async def verarbeite_outbox(*, max_anzahl: int = 20, jetzt: datetime | None = None) -> dict:
    """Ein Worker-Durchlauf. Mehrere Worker duerfen parallel laufen: SKIP LOCKED verteilt die Zeilen."""
    jetzt = jetzt or datetime.now(timezone.utc)
    stats = {"gesendet": 0, "wiederholt": 0, "fehlgeschlagen": 0, "abgebrochen_unklar": 0}
    stats["abgebrochen_unklar"] = await _bereinige_haengende(jetzt)
    for auftrag in await _beanspruche(max_anzahl, jetzt):
        try:
            await _versende(auftrag, jetzt, stats)
        except Exception:
            # Ergebnis nicht schreibbar (z. B. DB kurz weg): die Zeile bleibt "sending" und wird
            # vom Timeout als "Zustellung unbekannt" gemeldet -- die uebrigen Mails laufen weiter.
            logger.exception("Outbox-Mail %s: Ergebnis konnte nicht gespeichert werden", auftrag.id)
    return stats


async def wiederholen(session: AsyncSession, outbox_id: UUID, jetzt: datetime | None = None) -> MailOutbox | None:
    """Manueller Neustart einer endgueltig fehlgeschlagenen Mail (Admin-API)."""
    row = (await session.execute(
        select(MailOutbox).where(MailOutbox.id == outbox_id, MailOutbox.status == "failed").with_for_update()
    )).scalar_one_or_none()
    if row is None:
        return None
    row.status = "pending"
    row.versuche = 0
    row.naechster_versuch_am = jetzt or datetime.now(timezone.utc)
    if row.email_log_id:
        log = await session.get(EmailLog, row.email_log_id)
        if log is not None:
            log.status = "ausstehend"
            log.fehlermeldung = None
    await session.flush()
    return row
