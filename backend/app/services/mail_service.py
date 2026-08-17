import imaplib
import smtplib
from dataclasses import dataclass


class MailVerbindungFehler(Exception):
    """Verbindungsaufbau oder Login bei IMAP oder SMTP ist fehlgeschlagen --
    die Meldung enthaelt bewusst den urspruenglichen Fehler (falscher Host,
    falsches Passwort, Timeout, Zertifikatsproblem), damit der Nutzer beim
    Einrichten seines Postfachs eine brauchbare Fehlermeldung sieht statt
    eines generischen "Verbindung fehlgeschlagen"."""


@dataclass
class ImapZugang:
    host: str
    port: int
    verschluesselung: str  # "ssl" | "starttls" | "keine"
    benutzername: str
    passwort: str


@dataclass
class SmtpZugang:
    host: str
    port: int
    verschluesselung: str
    benutzername: str
    passwort: str


def _imap_login_blockierend(zugang: ImapZugang) -> None:
    if zugang.verschluesselung == "ssl":
        verbindung: imaplib.IMAP4 = imaplib.IMAP4_SSL(zugang.host, zugang.port, timeout=10)
    else:
        verbindung = imaplib.IMAP4(zugang.host, zugang.port, timeout=10)
        if zugang.verschluesselung == "starttls":
            verbindung.starttls()
    try:
        verbindung.login(zugang.benutzername, zugang.passwort)
        verbindung.select("INBOX", readonly=True)
    finally:
        try:
            verbindung.logout()
        except Exception:
            pass


def _smtp_login_blockierend(zugang: SmtpZugang) -> None:
    if zugang.verschluesselung == "ssl":
        verbindung: smtplib.SMTP = smtplib.SMTP_SSL(zugang.host, zugang.port, timeout=10)
    else:
        verbindung = smtplib.SMTP(zugang.host, zugang.port, timeout=10)
        if zugang.verschluesselung == "starttls":
            verbindung.starttls()
    try:
        verbindung.login(zugang.benutzername, zugang.passwort)
    finally:
        try:
            verbindung.quit()
        except Exception:
            pass


def pruefe_imap_verbindung(zugang: ImapZugang) -> None:
    """Blockierend -- vom Aufrufer per run_in_threadpool/anyio.to_thread
    auszufuehren, damit ein haengender Mailserver nicht den Event-Loop
    blockiert (gleiches Prinzip wie email_service._send_blocking)."""
    try:
        _imap_login_blockierend(zugang)
    except Exception as exc:
        raise MailVerbindungFehler(f"IMAP-Anmeldung fehlgeschlagen: {exc}") from exc


def pruefe_smtp_verbindung(zugang: SmtpZugang) -> None:
    try:
        _smtp_login_blockierend(zugang)
    except Exception as exc:
        raise MailVerbindungFehler(f"SMTP-Anmeldung fehlgeschlagen: {exc}") from exc
