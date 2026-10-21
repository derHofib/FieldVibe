import email
import hashlib
import logging
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
from app.services import e_rechnung_empfang_service as empfang
from app.services import storage_service
from app.services.mail_netz import verbinde_imap
from app.services.zuweisung_service import abrechnung_verantwortliche_user_ids

logger = logging.getLogger(__name__)

EMAIL_INGEST_AKTION = "eingangsrechnung_email_import_run"

# Je Mandant und Lauf hoechstens so viele Einzel-Benachrichtigungen ueber
# nicht importierbare Mails; der Rest wird in einer Sammelmeldung zusammengefasst.
_MAX_FEHLER_BENACHRICHTIGUNGEN = 10
# Merkliste bereits gemeldeter Anhaenge je Integration (siehe _fehler_schluessel).
_MAX_GEMELDETE_SCHLUESSEL = 200
_MAX_DETAILS = 100


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


def _xml_anhaenge(nachricht: email.message.Message) -> list[tuple[str, bytes]]:
    anhaenge = []
    for teil in nachricht.walk():
        dateiname = teil.get_filename()
        if not dateiname:
            continue
        if teil.get_content_type() not in ("application/xml", "text/xml") and not dateiname.lower().endswith(".xml"):
            continue
        payload = teil.get_payload(decode=True)
        if payload:
            anhaenge.append((_decode(dateiname), payload))
    return anhaenge


def _hat_anhang(nachricht: email.message.Message) -> bool:
    return any(teil.get_filename() for teil in nachricht.walk())


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

    verbindung = verbinde_imap(host, port, "ssl", 30)
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


def _fehler_schluessel(nachricht: email.message.Message, rohdaten: bytes, anhang: str | None, grund: str) -> str:
    # Die Mail-UID kennt dieser Pfad nicht (nur die Rohbytes); Message-ID bzw.
    # Hash der Rohnachricht identifiziert dieselbe Mail ebenso stabil.
    quelle = (nachricht.get("Message-ID") or "").strip().encode() or rohdaten
    return f"{hashlib.sha256(quelle).hexdigest()[:16]}:{anhang or '-'}:{grund}"


def _kurz(text: str, maximal: int = 300) -> str:
    text = " ".join(text.split())
    return text if len(text) <= maximal else text[: maximal - 1] + "…"




class _Lauf:
    """Zustand eines Importlaufs fuer EINE Integration (ein Postfach/Mandant).
    Die Zaehler gelten fuer den ganzen Lauf, die Merkliste fuer die Integration."""

    def __init__(self, session: AsyncSession, integration: MandantIntegration, zaehler: "_Zaehler"):
        self.session = session
        self.integration = integration
        self.zaehler = zaehler
        self._verantwortliche: list[User] | None = None
        self.gemeldet: list[str] = list(integration.config.get("gemeldete_import_fehler", []))
        self._einzelmeldungen = 0
        self.weitere = 0

    async def benachrichtige(self, titel: str, eingangsrechnung_id: UUID | None = None) -> None:
        if self._verantwortliche is None:
            self._verantwortliche = await _verantwortliche(self.session, self.integration.mandant_id)
        for user in self._verantwortliche:
            self.session.add(
                Notification(
                    mandant_id=self.integration.mandant_id,
                    user_id=user.id,
                    typ="eingangsrechnung",
                    titel=_kurz(titel),
                    ref_entity_type="eingangsrechnung" if eingangsrechnung_id else None,
                    ref_entity_id=eingangsrechnung_id,
                )
            )

    async def problem(
        self,
        mail: "_Mail",
        grund: str,
        anhang: str | None,
        meldung: str,
        eingangsrechnung_id: UUID | None = None,
    ) -> None:
        """Zaehlt den Fall und meldet ihn einmalig (Merkliste ueber Message-ID und
        Anhangname) mit begrenzter Zahl Einzelmeldungen je Lauf. Duplikate
        stehen nur im Ergebnis."""
        self.zaehler.vermerke(self.integration, mail, grund, anhang, meldung)
        if grund == "duplikat":
            return
        schluessel = _fehler_schluessel(mail.nachricht, mail.rohdaten, anhang, grund)
        if schluessel in self.gemeldet:
            return
        self.gemeldet.append(schluessel)
        if self._einzelmeldungen >= _MAX_FEHLER_BENACHRICHTIGUNGEN:
            self.weitere += 1
            return
        self._einzelmeldungen += 1
        if grund in ("kein_anhang", "kein_verwertbarer_anhang"):
            titel = f"E-Mail ohne Rechnungsanhang {mail.beschreibung}"
        else:
            wo = f"„{anhang}“ " if anhang else ""
            titel = f"Rechnung per E-Mail nicht vollständig importiert: {wo}{meldung} ({mail.beschreibung})"
        await self.benachrichtige(titel, eingangsrechnung_id)

    async def pdf_entwurf(self, mail: "_Mail", dateiname: str, pdf_bytes: bytes, hinweis: str | None = None) -> Eingangsrechnung:
        eingangsrechnung = Eingangsrechnung(
            mandant_id=self.integration.mandant_id,
            lieferant_name=mail.absender_anzeige,
            rechnungsnummer_lieferant="",
            rechnungsdatum=date.today(),
            betrag_netto=Decimal("0"),
            status="entwurf",
            email_absender=mail.absender_adresse or mail.absender_name or None,
            email_betreff=mail.betreff or None,
            import_hinweis=hinweis,
        )
        self.session.add(eingangsrechnung)
        await self.session.flush()

        key = storage_service.new_eingangsrechnung_beleg_key(eingangsrechnung.mandant_id, eingangsrechnung.id, dateiname)
        await storage_service.upload_bytes(key, pdf_bytes, "application/pdf")
        eingangsrechnung.beleg_object_key = key
        self.zaehler.neue_entwuerfe += 1
        return eingangsrechnung

    async def e_rechnung_importieren(
        self, mail: "_Mail", dateiname: str, daten: bytes, ist_hybrid_pdf: bool
    ) -> None:
        try:
            # SAVEPOINT: ein Datenbankfehler in einem Anhang darf die uebrigen Mails des Laufs nicht mitreissen.
            async with self.session.begin_nested():
                eingangsrechnung = await empfang.importiere_e_rechnung(
                    self.session,
                    mandant_id=self.integration.mandant_id,
                    erstellt_von=None,
                    daten=daten,
                    dateiname=dateiname,
                    email_absender=mail.absender_adresse or mail.absender_name or None,
                    email_betreff=mail.betreff or None,
                )
        except empfang.ERechnungDuplikat as exc:
            await self.problem(mail, "duplikat", dateiname, str(exc))
            return
        except empfang.ERechnungFehler as exc:
            meldung = "; ".join(exc.meldungen)
            entwurf_id = None
            if ist_hybrid_pdf:
                # Das PDF ist trotz kaputter XML eine lesbare Rechnung: als Entwurf mit
                # Hinweis behalten, statt sie zu verlieren.
                entwurf = await self.pdf_entwurf(mail, dateiname, daten, f"Eingebettete E-Rechnung nicht verwertbar: {meldung}")
                entwurf_id = entwurf.id
            await self.problem(mail, exc.grund, dateiname, meldung, entwurf_id)
            return
        except Exception:
            logger.exception("E-Rechnung-Import aus Anhang fehlgeschlagen")
            await self.problem(mail, "importfehler", dateiname, "Interner Fehler beim Import")
            return
        self.zaehler.neue_e_rechnungen += 1
        await self.benachrichtige(
            f"Neue E-Rechnung per E-Mail: {eingangsrechnung.lieferant_name}", eingangsrechnung.id
        )

    async def verarbeite(self, rohdaten: bytes) -> None:
        mail = _Mail(rohdaten)
        xml_anhaenge = _xml_anhaenge(mail.nachricht)
        pdf_anhaenge = _pdf_anhaenge(mail.nachricht)
        if not xml_anhaenge and not pdf_anhaenge:
            if _hat_anhang(mail.nachricht):
                await self.problem(mail, "kein_verwertbarer_anhang", None, "Anhang weder PDF noch XML")
            else:
                await self.problem(mail, "kein_anhang", None, "Kein Anhang")

        # XML zuerst: liegt dieselbe Rechnung zusaetzlich als Hybrid-PDF bei, erkennt
        # die Duplikatpruefung (Pruefsumme der XML) das PDF.
        for dateiname, xml_bytes in xml_anhaenge:
            await self.e_rechnung_importieren(mail, dateiname, xml_bytes, ist_hybrid_pdf=False)

        for dateiname, pdf_bytes in pdf_anhaenge:
            try:
                hat_xml = empfang.extrahiere_xml_aus_pdf(pdf_bytes) is not None
            except empfang.ERechnungFehler as exc:
                entwurf = await self.pdf_entwurf(mail, dateiname, pdf_bytes, f"E-Rechnung im PDF nicht geprüft: {exc}")
                await self.problem(mail, exc.grund, dateiname, str(exc), entwurf.id)
                continue
            if hat_xml:
                await self.e_rechnung_importieren(mail, dateiname, pdf_bytes, ist_hybrid_pdf=True)
                continue
            entwurf = await self.pdf_entwurf(mail, dateiname, pdf_bytes)
            await self.benachrichtige(f"Neue Rechnung per E-Mail: {mail.absender_anzeige}", entwurf.id)

    async def abschliessen(self, hoechste_uid: int) -> None:
        if self.weitere:
            await self.benachrichtige(
                f"E-Mail-Rechnungseingang: {self.weitere} weitere Mail(s) konnten nicht importiert werden – "
                "bitte das Postfach prüfen"
            )
        config = dict(self.integration.config)
        config["last_uid"] = hoechste_uid
        if self.gemeldet != list(self.integration.config.get("gemeldete_import_fehler", [])):
            config["gemeldete_import_fehler"] = self.gemeldet[-_MAX_GEMELDETE_SCHLUESSEL:]
        if config != self.integration.config:
            self.integration.config = config
        await self.session.flush()


class _Mail:
    def __init__(self, rohdaten: bytes):
        self.rohdaten = rohdaten
        self.nachricht = email.message_from_bytes(rohdaten)
        self.absender_name, self.absender_adresse = parseaddr(_decode(self.nachricht.get("From")))
        self.betreff = _decode(self.nachricht.get("Subject"))
        self.absender_anzeige = self.absender_name or self.absender_adresse or "Unbekannt"
        self.beschreibung = (
            f"von {self.absender_anzeige}, „{_kurz(self.betreff, 80)}“" if self.betreff else f"von {self.absender_anzeige}"
        )


class _Zaehler:
    def __init__(self) -> None:
        self.neue_entwuerfe = 0
        self.neue_e_rechnungen = 0
        self.fehler = 0
        self.uebersprungen: dict[str, int] = {}
        self.details: list[dict] = []

    def vermerke(
        self, integration: MandantIntegration, mail: _Mail, grund: str, anhang: str | None, meldung: str
    ) -> None:
        self.uebersprungen[grund] = self.uebersprungen.get(grund, 0) + 1
        if len(self.details) < _MAX_DETAILS:
            self.details.append(
                {
                    "mandant_id": str(integration.mandant_id),
                    "grund": grund,
                    "absender": mail.absender_anzeige,
                    "betreff": mail.betreff,
                    "anhang": anhang,
                    "meldung": meldung,
                }
            )


async def run_email_ingest(mandant_ids: list[UUID] | None = None) -> dict:
    """Stuendlicher Lauf (siehe app/worker.py): holt fuer jeden Mandanten mit
    aktiver IMAP-Integration neue E-Mails ab.

    - E-Rechnung (XML-Anhang oder Hybrid-PDF mit eingebetteter XML): legt eine
      Eingangsrechnung im Status 'offen' mit den Daten aus der XML an
      (e_rechnung_empfang_service).
    - Gewoehnliches PDF: Eingangsrechnung im Status 'entwurf' mit Platzhalter-
      Rechnungsnummer/-datum/-betrag -- die eigentliche Erfassung bestaetigt
      ein Mitarbeiter anschliessend im Rechnungseingang gegen den Beleg (siehe
      app/api/routes/eingangsrechnungen.py, Uebergang 'entwurf' -> 'offen').
    - Alles, woraus keine Rechnung wurde (kein Anhang, nicht lesbare oder
      unvollstaendige E-Rechnung, Fremdwaehrung, Duplikat), gilt NICHT still als
      erledigt: es steht je Grund im Ergebnis, und die Abrechnungs-
      Verantwortlichen werden benachrichtigt (Duplikate nur im Ergebnis). Die
      UID rueckt trotzdem vor, damit die Mail nicht jede Stunde erneut
      verarbeitet wird; sie bleibt im Postfach.

    Rueckgabe: neue_entwuerfe (PDF), neue_e_rechnungen, uebersprungen (Anzahl
    je Grund), uebersprungen_details (Mandant, Absender, Betreff, Anhang,
    Meldung), fehler (Abruf je Integration gescheitert)."""
    zaehler = _Zaehler()

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
                zaehler.fehler += 1
                continue

            lauf = _Lauf(session, integration, zaehler)
            for rohdaten in rohnachrichten:
                await lauf.verarbeite(rohdaten)
            await lauf.abschliessen(hoechste_uid)

        ergebnis = {
            "neue_entwuerfe": zaehler.neue_entwuerfe,
            "neue_e_rechnungen": zaehler.neue_e_rechnungen,
            "uebersprungen": zaehler.uebersprungen,
            "uebersprungen_details": zaehler.details,
            "fehler": zaehler.fehler,
        }
        session.add(
            AuditLog(
                mandant_id=None,
                actor_user_id=None,
                aktion=EMAIL_INGEST_AKTION,
                entity_type="scheduler",
                # Ohne Details: Absender/Betreff fremder Mandanten gehoeren nicht in den plattformweiten Log.
                payload={k: v for k, v in ergebnis.items() if k != "uebersprungen_details"},
            )
        )
        await session.flush()

    return ergebnis
