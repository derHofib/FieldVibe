import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

from starlette.concurrency import run_in_threadpool

from app.core.security import decrypt_secret
from app.models.mail_account import MailAccount


def _send_blockierend(
    *, host: str, port: int, verschluesselung: str, benutzername: str, passwort: str,
    nachricht: EmailMessage, empfaenger: list[str],
) -> None:
    if verschluesselung == "ssl":
        verbindung: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=20)
    else:
        verbindung = smtplib.SMTP(host, port, timeout=20)
        if verschluesselung == "starttls":
            verbindung.starttls()
    try:
        verbindung.login(benutzername, passwort)
        # to_addrs explizit -- sonst liest smtplib die Empfaenger aus den
        # To/Cc/Bcc-Kopfzeilen der Nachricht selbst. Bcc wird hier bewusst
        # NICHT als Kopfzeile gesetzt (siehe sende_nachricht), muss also so
        # ins SMTP-Envelope, sonst kaemen Bcc-Empfaenger die Mail nie an.
        verbindung.send_message(nachricht, to_addrs=empfaenger)
    finally:
        try:
            verbindung.quit()
        except Exception:
            pass


async def sende_nachricht(
    account: MailAccount,
    *,
    an: list[str],
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    betreff: str,
    text: str,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> None:
    """Baut eine RFC822-Nachricht und verschickt sie ueber die SMTP-Zugangs-
    daten des Postfachs. Legt bewusst KEINE lokale Kopie in mail_messages
    an -- die meisten Provider legen bei authentifiziertem SMTP-Versand
    automatisch eine Kopie im Gesendet-Ordner ab, die dann beim naechsten
    Mail-Sync-Tick (siehe worker.py, alle 2 Minuten) ganz regulaer auftaucht.
    Provider, die das nicht tun, sind ein bekannter, zurueckgestellter
    Rand fall (siehe PHASE_10 'Was offen bleibt') -- eine echte lokale
    Kopie vor dem naechsten Sync anzulegen wuerde entweder zu Duplikaten
    fuehren (Server legt doch eine Kopie an) oder eine komplexe
    Abgleichslogik zwischen "lokal gesendet" und "vom Server gesehen"
    brauchen, die fuer V1 nicht im Verhaeltnis zum Nutzen steht."""
    nachricht = EmailMessage()
    nachricht["Message-ID"] = make_msgid()
    nachricht["From"] = account.email_adresse
    nachricht["To"] = ", ".join(an)
    if cc:
        nachricht["Cc"] = ", ".join(cc)
    nachricht["Subject"] = betreff
    if in_reply_to:
        nachricht["In-Reply-To"] = in_reply_to
    if references:
        nachricht["References"] = references

    body = text
    if account.signatur:
        body = f"{text}\n\n--\n{account.signatur}"
    nachricht.set_content(body)

    passwort = decrypt_secret(account.passwort_verschluesselt)
    empfaenger = [*an, *(cc or []), *(bcc or [])]

    await run_in_threadpool(
        _send_blockierend,
        host=account.smtp_host,
        port=account.smtp_port,
        verschluesselung=account.smtp_verschluesselung,
        benutzername=account.smtp_benutzername,
        passwort=passwort,
        nachricht=nachricht,
        empfaenger=empfaenger,
    )
