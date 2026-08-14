import email
import imaplib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.header import decode_header
from email.message import Message
from email.utils import getaddresses, parseaddr, parsedate_to_datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.security import decrypt_secret
from app.db.session import system_session
from app.models.mail_account import MailAccount
from app.models.mail_attachment import MailAttachment
from app.models.mail_folder import MailFolder
from app.models.mail_message import MailMessage
from app.services import storage_service

# Schutz gegen einen Erst-Sync mit zehntausenden alten Nachrichten, der einen
# einzelnen Worker-Tick blockieren wuerde -- last_uid ist bereits der
# Fortschrittszeiger, der naechste Tick (siehe app/worker.py) macht einfach
# an dieser Stelle weiter.
MAX_NACHRICHTEN_PRO_ORDNER_UND_LAUF = 200

_LIST_RESPONSE_MUSTER = re.compile(r'^\((?P<flags>[^)]*)\)\s+"(?P<delimiter>.*)"\s+(?P<name>.+)$')


def _decode(value: str | None) -> str:
    if not value:
        return ""
    teile = decode_header(value)
    return "".join(
        teil.decode(zeichensatz or "utf-8", errors="replace") if isinstance(teil, bytes) else teil
        for teil, zeichensatz in teile
    )


def _entpacke_adressliste(nachricht: Message, header: str) -> list[str]:
    rohwert = nachricht.get(header)
    if not rohwert:
        return []
    return [
        f"{name} <{adresse}>" if name else adresse
        for name, adresse in getaddresses([_decode(rohwert)])
        if adresse
    ]


def _parse_list_zeile(zeile: bytes) -> tuple[list[str], str, str] | None:
    # imaplib liefert list() nicht strukturiert -- typisches Format:
    # b'(\\HasNoChildren) "/" "INBOX"' bzw. ohne Anfuehrungszeichen bei
    # Namen ohne Leerzeichen. Namen mit Nicht-ASCII-Zeichen sind IMAP-UTF-7-
    # kodiert und werden hier bewusst nicht dekodiert (siehe Docstring
    # von sync_account) -- betrifft nur die Anzeige, nicht die Funktion.
    text = zeile.decode("utf-8", errors="replace")
    treffer = _LIST_RESPONSE_MUSTER.match(text)
    if not treffer:
        return None
    flags = treffer.group("flags").split()
    delimiter = treffer.group("delimiter")
    name = treffer.group("name").strip()
    if name.startswith('"') and name.endswith('"'):
        name = name[1:-1]
    return flags, delimiter, name


def _anzeigename(imap_name: str, delimiter: str) -> str:
    if imap_name.upper() == "INBOX":
        return "Posteingang"
    teile = imap_name.split(delimiter) if delimiter else [imap_name]
    return teile[-1] or imap_name


@dataclass
class RohNachricht:
    uid: int
    rohdaten: bytes
    gelesen: bool


@dataclass
class OrdnerSyncErgebnis:
    imap_name: str
    anzeigename: str
    delimiter: str
    uidvalidity: int
    zuruckgesetzt: bool  # UIDVALIDITY hat sich geaendert -- Aufrufer muss alte Nachrichten des Ordners loeschen
    neue_uid_grenze: int
    nachrichten: list[RohNachricht] = field(default_factory=list)


def _parse_fetch_flags(meta: bytes) -> bool:
    treffer = re.search(rb"FLAGS \(([^)]*)\)", meta)
    if not treffer:
        return False
    return b"\\Seen" in treffer.group(1)


def _imap_verbinden_blockierend(account: MailAccount, passwort: str) -> imaplib.IMAP4:
    if account.imap_verschluesselung == "ssl":
        verbindung: imaplib.IMAP4 = imaplib.IMAP4_SSL(account.imap_host, account.imap_port, timeout=20)
    else:
        verbindung = imaplib.IMAP4(account.imap_host, account.imap_port, timeout=20)
        if account.imap_verschluesselung == "starttls":
            verbindung.starttls()
    verbindung.login(account.imap_benutzername, passwort)
    return verbindung


def _sync_account_blockierend(
    account: MailAccount, passwort: str, bekannte_ordner: dict[str, tuple[int | None, int]]
) -> list[OrdnerSyncErgebnis]:
    """Blockierend -- vom Aufrufer per run_in_threadpool auszufuehren.
    bekannte_ordner: imap_name -> (uidvalidity, last_uid) aus der DB, damit
    die gesamte Synchronisation in einer einzigen Verbindung und einem
    einzigen Thread-Sprung passiert statt einem Sprung je Ordner."""
    verbindung = _imap_verbinden_blockierend(account, passwort)
    ergebnisse: list[OrdnerSyncErgebnis] = []
    try:
        status_code, daten = verbindung.list()
        if status_code != "OK":
            return ergebnisse

        for zeile in daten:
            geparst = _parse_list_zeile(zeile) if isinstance(zeile, bytes) else None
            if geparst is None:
                continue
            flags, delimiter, imap_name = geparst
            if "\\Noselect" in flags:
                continue

            status_code, _ = verbindung.select(imap_name, readonly=True)
            if status_code != "OK":
                continue

            status_code, uidvalidity_daten = verbindung.response("UIDVALIDITY")
            uidvalidity = 0
            if uidvalidity_daten and uidvalidity_daten[0]:
                try:
                    uidvalidity = int(uidvalidity_daten[0])
                except (TypeError, ValueError):
                    uidvalidity = 0

            bekannte_uidvalidity, last_uid = bekannte_ordner.get(imap_name, (None, 0))
            zuruckgesetzt = bekannte_uidvalidity is not None and bekannte_uidvalidity != uidvalidity
            such_ab = 1 if zuruckgesetzt else last_uid + 1

            status_code, such_daten = verbindung.uid("search", None, f"UID {such_ab}:*")
            uids: list[int] = []
            if status_code == "OK" and such_daten and such_daten[0]:
                uids = sorted({u for u in (int(x) for x in such_daten[0].split()) if u >= such_ab})

            neue_uid_grenze = last_uid if not zuruckgesetzt else 0
            nachrichten: list[RohNachricht] = []
            for uid in uids[:MAX_NACHRICHTEN_PRO_ORDNER_UND_LAUF]:
                status_code, rohdaten = verbindung.uid("fetch", str(uid), "(RFC822 FLAGS)")
                if status_code != "OK":
                    continue
                for teil in rohdaten:
                    if isinstance(teil, tuple) and len(teil) == 2:
                        gelesen = _parse_fetch_flags(teil[0])
                        nachrichten.append(RohNachricht(uid=uid, rohdaten=teil[1], gelesen=gelesen))
                        break
                neue_uid_grenze = max(neue_uid_grenze, uid)

            ergebnisse.append(
                OrdnerSyncErgebnis(
                    imap_name=imap_name,
                    anzeigename=_anzeigename(imap_name, delimiter),
                    delimiter=delimiter,
                    uidvalidity=uidvalidity,
                    zuruckgesetzt=zuruckgesetzt,
                    neue_uid_grenze=neue_uid_grenze,
                    nachrichten=nachrichten,
                )
            )
        return ergebnisse
    finally:
        try:
            verbindung.logout()
        except Exception:
            pass


def _mail_datum(nachricht: Message) -> datetime | None:
    rohwert = nachricht.get("Date")
    if not rohwert:
        return None
    try:
        geparst = parsedate_to_datetime(rohwert)
    except (TypeError, ValueError):
        return None
    if geparst is None:
        return None
    if geparst.tzinfo is None:
        geparst = geparst.replace(tzinfo=timezone.utc)
    return geparst


def _koerper(nachricht: Message) -> tuple[str | None, str | None]:
    text_teil: str | None = None
    html_teil: str | None = None
    if nachricht.is_multipart():
        for teil in nachricht.walk():
            if teil.get_content_disposition() == "attachment":
                continue
            content_type = teil.get_content_type()
            payload = teil.get_payload(decode=True)
            if payload is None:
                continue
            zeichensatz = teil.get_content_charset() or "utf-8"
            dekodiert = payload.decode(zeichensatz, errors="replace")
            if content_type == "text/plain" and text_teil is None:
                text_teil = dekodiert
            elif content_type == "text/html" and html_teil is None:
                html_teil = dekodiert
    else:
        payload = nachricht.get_payload(decode=True)
        if payload is not None:
            zeichensatz = nachricht.get_content_charset() or "utf-8"
            dekodiert = payload.decode(zeichensatz, errors="replace")
            if nachricht.get_content_type() == "text/html":
                html_teil = dekodiert
            else:
                text_teil = dekodiert
    return text_teil, html_teil


def _anhaenge(nachricht: Message) -> list[tuple[str, bytes, str, bool]]:
    ergebnisse = []
    if not nachricht.is_multipart():
        return ergebnisse
    for teil in nachricht.walk():
        dateiname = teil.get_filename()
        content_disposition = teil.get_content_disposition()
        if not dateiname and content_disposition != "attachment":
            continue
        payload = teil.get_payload(decode=True)
        if not payload:
            continue
        ergebnisse.append(
            (
                _decode(dateiname) or "anhang.bin",
                payload,
                teil.get_content_type() or "application/octet-stream",
                content_disposition == "inline",
            )
        )
    return ergebnisse


async def _upsert_ordner(session: AsyncSession, account: MailAccount, ergebnis: OrdnerSyncErgebnis) -> MailFolder:
    stmt = select(MailFolder).where(
        MailFolder.mail_account_id == account.id, MailFolder.imap_name == ergebnis.imap_name
    )
    ordner = (await session.execute(stmt)).scalar_one_or_none()
    if ordner is None:
        ordner = MailFolder(
            mandant_id=account.mandant_id,
            mail_account_id=account.id,
            imap_name=ergebnis.imap_name,
            anzeigename=ergebnis.anzeigename,
            uidvalidity=ergebnis.uidvalidity,
            last_uid=ergebnis.neue_uid_grenze,
            letzter_sync_am=datetime.now(timezone.utc),
        )
        session.add(ordner)
        await session.flush()
    else:
        if ergebnis.zuruckgesetzt:
            await session.execute(delete(MailMessage).where(MailMessage.folder_id == ordner.id))
        ordner.uidvalidity = ergebnis.uidvalidity
        ordner.last_uid = max(ordner.last_uid if not ergebnis.zuruckgesetzt else 0, ergebnis.neue_uid_grenze)
        ordner.letzter_sync_am = datetime.now(timezone.utc)
        ordner.anzeigename = ergebnis.anzeigename
    return ordner


async def _speichere_nachricht(
    session: AsyncSession, account: MailAccount, ordner: MailFolder, roh: RohNachricht
) -> None:
    geparst = email.message_from_bytes(roh.rohdaten)
    von_name, von_adresse = parseaddr(_decode(geparst.get("From")))
    text_teil, html_teil = _koerper(geparst)

    nachricht = MailMessage(
        mandant_id=account.mandant_id,
        mail_account_id=account.id,
        folder_id=ordner.id,
        uid=roh.uid,
        message_id_header=geparst.get("Message-ID"),
        in_reply_to=geparst.get("In-Reply-To"),
        references_header=geparst.get("References"),
        von_name=von_name or None,
        von_adresse=von_adresse or None,
        an=_entpacke_adressliste(geparst, "To"),
        cc=_entpacke_adressliste(geparst, "Cc"),
        betreff=_decode(geparst.get("Subject")),
        body_text=text_teil,
        body_html=html_teil,
        datum=_mail_datum(geparst),
        gelesen=roh.gelesen,
    )
    session.add(nachricht)
    await session.flush()

    for dateiname, inhalt, mimetype, eingebettet in _anhaenge(geparst):
        key = storage_service.new_mail_attachment_key(nachricht.id, dateiname)
        await storage_service.upload_bytes(key, inhalt, mimetype)
        session.add(
            MailAttachment(
                mandant_id=account.mandant_id,
                message_id=nachricht.id,
                dateiname=dateiname,
                mimetype=mimetype,
                groesse_bytes=len(inhalt),
                object_key=key,
                eingebettet=eingebettet,
            )
        )


async def sync_account(session: AsyncSession, account: MailAccount) -> dict:
    """Synchronisiert alle Ordner eines Postfachs inkrementell. Nicht-ASCII-
    Ordnernamen werden unveraendert (nicht IMAP-UTF-7-dekodiert) angezeigt --
    ein bewusst zurueckgestellter Rand fall, siehe PHASE_10 'Was offen
    bleibt'. Wirft keine Exception nach aussen, sondern schreibt Fehler in
    account.letzter_sync_fehler, damit ein einzelnes kaputtes Postfach nicht
    den Sync-Lauf der anderen Konten im selben Tick abbricht (siehe
    run_mail_sync)."""
    ordner_rows = (
        (await session.execute(select(MailFolder).where(MailFolder.mail_account_id == account.id)))
        .scalars()
        .all()
    )
    bekannte_ordner = {o.imap_name: (o.uidvalidity, o.last_uid) for o in ordner_rows}

    passwort = decrypt_secret(account.passwort_verschluesselt)
    ergebnisse = await run_in_threadpool(_sync_account_blockierend, account, passwort, bekannte_ordner)

    neue_nachrichten = 0
    for index, ergebnis in enumerate(ergebnisse):
        ordner = await _upsert_ordner(session, account, ergebnis)
        ordner.sortierung = 0 if ergebnis.imap_name.upper() == "INBOX" else index + 1
        for roh in ergebnis.nachrichten:
            await _speichere_nachricht(session, account, ordner, roh)
            neue_nachrichten += 1

    account.letzter_sync_am = datetime.now(timezone.utc)
    account.letzter_sync_fehler = None
    await session.flush()
    return {"ordner": len(ergebnisse), "neue_nachrichten": neue_nachrichten}


async def run_mail_sync(account_ids: list | None = None) -> dict:
    """Periodischer Sync-Lauf, siehe app/worker.py -- laeuft in einem
    eigenen, kurzen Takt (nicht dem stuendlichen Scheduler-Tick), weil ein
    persoenliches Postfach staerker als der Rechnungseingang-Import unter
    einer stundenlangen Verzoegerung leidet."""
    konten_synchronisiert = 0
    fehler = 0

    async with system_session() as session:
        stmt = select(MailAccount).where(MailAccount.aktiv.is_(True))
        if account_ids is not None:
            stmt = stmt.where(MailAccount.id.in_(account_ids))
        konten = (await session.execute(stmt)).scalars().all()

        for account in konten:
            try:
                await sync_account(session, account)
                konten_synchronisiert += 1
            except Exception as exc:
                fehler += 1
                account.letzter_sync_fehler = str(exc)
                await session.flush()

    return {"konten_synchronisiert": konten_synchronisiert, "fehler": fehler}
