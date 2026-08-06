import email
import imaplib
from datetime import date
from decimal import Decimal
from email.header import decode_header
from email.utils import parseaddr
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.security import decrypt_secret
from app.db.session import system_session
from app.models.audit_log import AuditLog
from app.models.eingangsrechnung import Eingangsrechnung
from app.models.integration import MandantIntegration
from app.models.notification import Notification
from app.models.user import User
from app.services import storage_service
from app.services.zuweisung_service import abrechnung_verantwortliche_user_ids

EMAIL_INGEST_AKTION = "eingangsrechnung_email_import_run"


def _decode(value: str | None) -> str:
    if not value:
        return ""
    teile = decode_header(value)
    return "".join(
        teil.decode(zeichensatz or "utf-8", errors="replace") if isinstance(teil, bytes) else teil
        for teil, zeichensatz in teile
    )


def _pdf_anhaenge(nachricht: email.message.Message) -> list[tuple[str, bytes]]:
    anhaenge = []
    for teil in nachricht.walk():
        dateiname = teil.get_filename()
        if teil.get_content_type() != "application/pdf" and not (
            dateiname and dateiname.lower().endswith(".pdf")
        ):
            continue
        payload = teil.get_payload(decode=True)
        if payload:
            anhaenge.append((_decode(dateiname) or "rechnung.pdf", payload))
    return anhaenge


def _fetch_neue_nachrichten(integration: MandantIntegration) -> tuple[list[bytes], int]:
    """Blockierender IMAP-Zugriff -- wird per run_in_threadpool aufgerufen,
    damit ein haengender/langsamer Mailserver nicht den Event-Loop blockiert.

    UID-basierte Inkrementalsuche (statt \\Seen-Flag) ab der zuletzt
    verarbeiteten UID (integration.config["last_uid"]) -- funktioniert auch,
    wenn dasselbe Postfach parallel in einem echten Mail-Client gelesen
    wird, ohne Nachrichten doppelt oder gar nicht zu verarbeiten. Ein
    Wechsel der Mailbox-UIDVALIDITY (z.B. nach einem Server-Wechsel) wird
    bewusst nicht gesondert behandelt -- fuer ein dediziertes
    Rechnungseingang-Postfach ein akzeptabler Rand fall."""
    config = integration.config
    host = config["host"]
    port = int(config.get("port", 993))
    user = config["user"]
    passwort = decrypt_secret(integration.secret_ref) if integration.secret_ref else ""
    mailbox = config.get("mailbox", "INBOX")
    last_uid = int(config.get("last_uid", 0))

    verbindung = imaplib.IMAP4_SSL(host, port)
    try:
        verbindung.login(user, passwort)
        verbindung.select(mailbox)

        status_code, daten = verbindung.uid("search", None, f"UID {last_uid + 1}:*")
        if status_code != "OK" or not daten or not daten[0]:
            return [], last_uid

        uids = sorted({int(u) for u in daten[0].split() if int(u) > last_uid})
        nachrichten: list[bytes] = []
        hoechste_uid = last_uid
        for uid in uids:
            status_code, rohdaten = verbindung.uid("fetch", str(uid), "(RFC822)")
            if status_code == "OK":
                for teil in rohdaten:
                    if isinstance(teil, tuple):
                        nachrichten.append(teil[1])
                        break
            hoechste_uid = max(hoechste_uid, uid)
        return nachrichten, hoechste_uid
    finally:
        try:
            verbindung.logout()
        except Exception:
            pass


async def _verantwortliche(session: AsyncSession, mandant_id: UUID) -> list[User]:
    user_ids = await abrechnung_verantwortliche_user_ids(session, mandant_id)
    if not user_ids:
        return []
    result = await session.execute(select(User).where(User.id.in_(user_ids)))
    return list(result.scalars().all())


async def run_email_ingest(mandant_ids: list[UUID] | None = None) -> dict:
    """Stuendlicher Lauf (siehe app/worker.py): holt fuer jeden Mandanten mit
    aktiver IMAP-Integration neue E-Mails ab und legt fuer jeden PDF-Anhang
    eine Eingangsrechnung im Status 'entwurf' an (Platzhalter-Rechnungsnummer/
    -datum/-betrag) -- die eigentliche Erfassung (Lieferant, Betrag,
    Rechnungsnummer) bestaetigt ein Mitarbeiter anschliessend im
    Rechnungseingang gegen den mitgelieferten Beleg (siehe
    app/api/routes/eingangsrechnungen.py, Uebergang 'entwurf' -> 'offen').
    Mails ohne PDF-Anhang werden ignoriert, aber trotzdem als verarbeitet
    markiert (kein endloses Wiederholen bei reiner Werbe-/Spam-Post)."""
    neue_entwuerfe = 0
    fehler = 0

    async with system_session() as session:
        stmt = select(MandantIntegration).where(
            MandantIntegration.typ == "imap", MandantIntegration.aktiv.is_(True)
        )
        if mandant_ids is not None:
            stmt = stmt.where(MandantIntegration.mandant_id.in_(mandant_ids))
        integrationen = (await session.execute(stmt)).scalars().all()

        for integration in integrationen:
            try:
                rohnachrichten, hoechste_uid = await run_in_threadpool(
                    _fetch_neue_nachrichten, integration
                )
            except Exception:
                fehler += 1
                continue

            verantwortliche: list[User] | None = None
            for rohdaten in rohnachrichten:
                nachricht = email.message_from_bytes(rohdaten)
                absender_name, absender_adresse = parseaddr(_decode(nachricht.get("From")))
                betreff = _decode(nachricht.get("Subject"))

                for dateiname, pdf_bytes in _pdf_anhaenge(nachricht):
                    eingangsrechnung = Eingangsrechnung(
                        mandant_id=integration.mandant_id,
                        lieferant_name=absender_name or absender_adresse or "Unbekannt",
                        rechnungsnummer_lieferant="",
                        rechnungsdatum=date.today(),
                        betrag_netto=Decimal("0"),
                        status="entwurf",
                        email_absender=absender_adresse or absender_name or None,
                        email_betreff=betreff or None,
                    )
                    session.add(eingangsrechnung)
                    await session.flush()

                    key = storage_service.new_eingangsrechnung_beleg_key(eingangsrechnung.id, dateiname)
                    await storage_service.upload_bytes(key, pdf_bytes, "application/pdf")
                    eingangsrechnung.beleg_object_key = key
                    neue_entwuerfe += 1

                    if verantwortliche is None:
                        verantwortliche = await _verantwortliche(session, integration.mandant_id)
                    for user in verantwortliche:
                        session.add(
                            Notification(
                                mandant_id=integration.mandant_id,
                                user_id=user.id,
                                typ="eingangsrechnung",
                                titel=f"Neue Rechnung per E-Mail: {absender_name or absender_adresse or 'Unbekannt'}",
                                ref_entity_type="eingangsrechnung",
                                ref_entity_id=eingangsrechnung.id,
                            )
                        )

            if hoechste_uid != int(integration.config.get("last_uid", 0)):
                integration.config = {**integration.config, "last_uid": hoechste_uid}
            await session.flush()

        ergebnis = {"neue_entwuerfe": neue_entwuerfe, "fehler": fehler}
        session.add(
            AuditLog(
                mandant_id=None,
                actor_user_id=None,
                aktion=EMAIL_INGEST_AKTION,
                entity_type="scheduler",
                payload=ergebnis,
            )
        )
        await session.flush()

    return ergebnis
