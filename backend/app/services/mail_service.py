from dataclasses import dataclass

from app.services.mail_netz import (
    MailVerbindungFehler,
    pruefe_ziel,
    uebersetze_fehler,
    verbinde_imap,
    verbinde_smtp,
)

__all__ = [
    "ImapZugang",
    "MailVerbindungFehler",
    "SmtpZugang",
    "pruefe_imap_verbindung",
    "pruefe_smtp_verbindung",
    "pruefe_imap_ziel",
    "pruefe_smtp_ziel",
]


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
    verbindung = verbinde_imap(zugang.host, zugang.port, zugang.verschluesselung, 10)
    try:
        verbindung.login(zugang.benutzername, zugang.passwort)
        verbindung.select("INBOX", readonly=True)
    finally:
        try:
            verbindung.logout()
        except Exception:
            pass


def _smtp_login_blockierend(zugang: SmtpZugang) -> None:
    verbindung = verbinde_smtp(zugang.host, zugang.port, zugang.verschluesselung, 10)
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
        raise uebersetze_fehler(exc, "imap") from exc


def pruefe_smtp_verbindung(zugang: SmtpZugang) -> None:
    try:
        _smtp_login_blockierend(zugang)
    except Exception as exc:
        raise uebersetze_fehler(exc, "smtp") from exc


def pruefe_imap_ziel(host: str, port: int) -> None:
    """Fuer die Routen (Anlegen/Aendern/Testen): Ziel schon vor dem
    Speichern ablehnen. Blockierend (DNS)."""
    pruefe_ziel(host, port, "imap")


def pruefe_smtp_ziel(host: str, port: int) -> None:
    pruefe_ziel(host, port, "smtp")
