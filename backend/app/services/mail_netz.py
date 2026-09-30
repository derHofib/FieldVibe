"""Gemeinsamer Verbindungsaufbau fuer IMAP/SMTP: Zielpruefung (SSRF),
verifizierendes TLS und generische Fehlermeldungen."""
import imaplib
import ipaddress
import logging
import smtplib
import socket
import ssl
from typing import Literal

from app.core.config import get_settings

logger = logging.getLogger(__name__)

Protokoll = Literal["imap", "smtp"]


class MailVerbindungFehler(Exception):
    """Verbindungsaufbau oder Login bei IMAP oder SMTP ist fehlgeschlagen.
    Die Meldung ist bewusst generisch und darf an den Aufrufer zurueck --
    Banner, rohe Exception-Texte und aufgeloeste Adressen stehen nur im Log
    (sonst taugt der Test-Endpunkt als Port-Scanner/Banner-Orakel)."""


def _erlaubte_ports(protokoll: Protokoll) -> set[int]:
    settings = get_settings()
    roh = settings.mail_erlaubte_imap_ports if protokoll == "imap" else settings.mail_erlaubte_smtp_ports
    return {int(p) for p in roh.split(",") if p.strip().isdigit()}


def _aufloesen(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    # Zonen-Suffix (fe80::1%eth0) wuerde ip_address() nicht parsen.
    return [str(info[4][0]).split("%")[0] for info in infos]


def _ist_oeffentlich(adresse: str) -> bool:
    ip = ipaddress.ip_address(adresse)
    # ::ffff:10.0.0.1 wuerde sonst als "global" durchrutschen.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
        or ip.is_reserved or ip.is_unspecified
    ):
        return False
    # Faengt u.a. Carrier-grade NAT (100.64/10) ab, das is_private nicht kennt.
    return ip.is_global


def pruefe_ziel(host: str, port: int, protokoll: Protokoll) -> str:
    """Prueft Port-Allowlist und aufgeloeste Adressen und liefert die IP,
    mit der verbunden werden soll (gegen DNS-Rebinding: der Aufrufer
    verbindet auf genau diese IP statt erneut aufzuloesen)."""
    if port not in _erlaubte_ports(protokoll):
        raise MailVerbindungFehler("Verbindung fehlgeschlagen: Port nicht erlaubt")
    if not host or not host.strip():
        raise MailVerbindungFehler("Verbindung fehlgeschlagen: Server nicht erreichbar")
    try:
        adressen = _aufloesen(host.strip(), port)
        for adresse in adressen:
            ipaddress.ip_address(adresse)
    except (OSError, ValueError, UnicodeError) as exc:
        logger.warning("Mail-Ziel %s:%s nicht aufloesbar: %s", host, port, exc)
        raise MailVerbindungFehler("Verbindung fehlgeschlagen: Server nicht erreichbar") from exc
    if not adressen:
        raise MailVerbindungFehler("Verbindung fehlgeschlagen: Server nicht erreichbar")
    if not get_settings().mail_erlaube_private_hosts:
        for adresse in adressen:
            if not _ist_oeffentlich(adresse):
                logger.warning("Mail-Ziel %s:%s geblockt (nicht oeffentliche Adresse %s)", host, port, adresse)
                raise MailVerbindungFehler("Verbindung fehlgeschlagen: Server nicht erlaubt")
    return adressen[0]


def ssl_kontext() -> ssl.SSLContext:
    return ssl.create_default_context()


def _verbinde_socket(ip: str, port: int, timeout: float | None) -> socket.socket:
    return socket.create_connection((ip, port), timeout)


class _ImapGepinnt(imaplib.IMAP4):
    def __init__(self, host: str, port: int, *, ip: str, timeout: float) -> None:
        self._ip = ip
        super().__init__(host, port, timeout)

    def _create_socket(self, timeout):  # type: ignore[override]
        return _verbinde_socket(self._ip, self.port, timeout)


class _ImapSslGepinnt(imaplib.IMAP4_SSL):
    def __init__(self, host: str, port: int, *, ip: str, timeout: float) -> None:
        self._ip = ip
        super().__init__(host, port, ssl_context=ssl_kontext(), timeout=timeout)

    def _create_socket(self, timeout):  # type: ignore[override]
        sock = _verbinde_socket(self._ip, self.port, timeout)
        # server_hostname bleibt der Name, nicht die IP -- sonst prueft TLS
        # das Zertifikat gegen die falsche Identitaet.
        return self.ssl_context.wrap_socket(sock, server_hostname=self.host)


class _SmtpGepinnt(smtplib.SMTP):
    def __init__(self, host: str, port: int, *, ip: str, timeout: float) -> None:
        self._ip = ip
        super().__init__(host, port, timeout=timeout)

    def _get_socket(self, host, port, timeout):  # type: ignore[override]
        return _verbinde_socket(self._ip, port, timeout)


class _SmtpSslGepinnt(smtplib.SMTP_SSL):
    def __init__(self, host: str, port: int, *, ip: str, timeout: float) -> None:
        self._ip = ip
        super().__init__(host, port, timeout=timeout, context=ssl_kontext())

    def _get_socket(self, host, port, timeout):  # type: ignore[override]
        sock = _verbinde_socket(self._ip, port, timeout)
        return self.context.wrap_socket(sock, server_hostname=self._host)


def verbinde_imap(host: str, port: int, verschluesselung: str, timeout: float) -> imaplib.IMAP4:
    ip = pruefe_ziel(host, port, "imap")
    if verschluesselung == "ssl":
        return _ImapSslGepinnt(host, port, ip=ip, timeout=timeout)
    verbindung = _ImapGepinnt(host, port, ip=ip, timeout=timeout)
    if verschluesselung == "starttls":
        verbindung.starttls(ssl_context=ssl_kontext())
    return verbindung


def verbinde_smtp(host: str, port: int, verschluesselung: str, timeout: float) -> smtplib.SMTP:
    ip = pruefe_ziel(host, port, "smtp")
    if verschluesselung == "ssl":
        return _SmtpSslGepinnt(host, port, ip=ip, timeout=timeout)
    verbindung = _SmtpGepinnt(host, port, ip=ip, timeout=timeout)
    if verschluesselung == "starttls":
        verbindung.starttls(context=ssl_kontext())
    return verbindung


def uebersetze_fehler(exc: Exception, protokoll: Protokoll) -> MailVerbindungFehler:
    """Mappt beliebige Fehler beim Verbindungsaufbau/Login auf eine
    generische Meldung; das Original landet nur im Log."""
    if isinstance(exc, MailVerbindungFehler):
        return exc
    logger.warning("%s-Verbindung fehlgeschlagen: %s: %s", protokoll.upper(), type(exc).__name__, exc)
    if isinstance(exc, ssl.SSLError):
        return MailVerbindungFehler("Verbindung fehlgeschlagen: Zertifikat ungültig")
    if isinstance(exc, (smtplib.SMTPAuthenticationError, imaplib.IMAP4.error)):
        return MailVerbindungFehler("Verbindung fehlgeschlagen: Anmeldung abgelehnt")
    return MailVerbindungFehler("Verbindung fehlgeschlagen: Server nicht erreichbar")
