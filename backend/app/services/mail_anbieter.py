from dataclasses import dataclass

import dns.asyncresolver

from app.models.mail_account import MailAccount


@dataclass(frozen=True)
class MailAnbieter:
    id: str
    name: str
    kuerzel: str
    farbe: str
    beschreibung: str
    domains: tuple[str, ...]
    mx_suffixe: tuple[str, ...]
    imap_host: str
    imap_port: int
    imap_verschluesselung: str
    smtp_host: str
    smtp_port: int
    smtp_verschluesselung: str
    hinweis: str | None = None
    unterstuetzt: bool = True


# Reihenfolge = Reihenfolge der Kacheln im Frontend. Der Benutzername ist bei
# allen Anbietern die volle E-Mail-Adresse. Werte laut Hilfeseiten der Anbieter.
ANBIETER: tuple[MailAnbieter, ...] = (
    # IONOS-Hilfe "E-Mail-Programm einrichten"; 1&1-Postfächer laufen auf denselben Servern.
    MailAnbieter(
        id="ionos", name="IONOS", kuerzel="IO", farbe="#003D8F",
        beschreibung="eigene Domain, 1&1",
        domains=("online.de", "1und1.de"),
        mx_suffixe=(".ionos.de", ".kundenserver.de", ".1and1.com"),
        imap_host="imap.ionos.de", imap_port=993, imap_verschluesselung="ssl",
        smtp_host="smtp.ionos.de", smtp_port=587, smtp_verschluesselung="starttls",
        hinweis="Das Passwort des Postfachs eingeben, nicht das Passwort des IONOS-Kundenkontos.",
    ),
    MailAnbieter(
        id="strato", name="STRATO", kuerzel="ST", farbe="#FF8200",
        beschreibung="eigene Domain",
        domains=(),
        mx_suffixe=(".rzone.de",),
        imap_host="imap.strato.de", imap_port=993, imap_verschluesselung="ssl",
        smtp_host="smtp.strato.de", smtp_port=465, smtp_verschluesselung="ssl",
        hinweis="Das Passwort des Postfachs eingeben, nicht das Passwort des STRATO-Kundenkontos.",
    ),
    MailAnbieter(
        id="telekom", name="Telekom", kuerzel="T", farbe="#E20074",
        beschreibung="t-online.de, magenta.de",
        domains=("t-online.de", "magenta.de"),
        mx_suffixe=(),
        imap_host="secureimap.t-online.de", imap_port=993, imap_verschluesselung="ssl",
        smtp_host="securesmtp.t-online.de", smtp_port=465, smtp_verschluesselung="ssl",
        hinweis="Das E-Mail-Passwort aus dem Kundencenter eingeben, nicht das Login-Passwort.",
    ),
    MailAnbieter(
        id="gmx", name="GMX", kuerzel="GX", farbe="#1C449B",
        beschreibung="gmx.de, gmx.net",
        domains=("gmx.de", "gmx.net", "gmx.at", "gmx.ch"),
        mx_suffixe=(),
        imap_host="imap.gmx.net", imap_port=993, imap_verschluesselung="ssl",
        smtp_host="mail.gmx.net", smtp_port=587, smtp_verschluesselung="starttls",
        hinweis="Im GMX-Postfach unter Einstellungen den Abruf per IMAP/POP3 zuerst freischalten.",
    ),
    MailAnbieter(
        id="webde", name="WEB.DE", kuerzel="WD", farbe="#FFD800",
        beschreibung="web.de",
        domains=("web.de",),
        mx_suffixe=(),
        imap_host="imap.web.de", imap_port=993, imap_verschluesselung="ssl",
        smtp_host="smtp.web.de", smtp_port=587, smtp_verschluesselung="starttls",
        hinweis="Im WEB.DE-Postfach unter Einstellungen den Abruf per IMAP/POP3 zuerst freischalten.",
    ),
    # Google-Hilfe "E-Mail in anderen Clients lesen": IMAP 993 SSL, SMTP 465 SSL.
    MailAnbieter(
        id="google", name="Gmail / Google Workspace", kuerzel="G", farbe="#EA4335",
        beschreibung="gmail.com, Google Workspace",
        domains=("gmail.com", "googlemail.com"),
        mx_suffixe=(".google.com", ".googlemail.com"),
        imap_host="imap.gmail.com", imap_port=993, imap_verschluesselung="ssl",
        smtp_host="smtp.gmail.com", smtp_port=465, smtp_verschluesselung="ssl",
        hinweis="Ein App-Passwort verwenden (dafür muss die Bestätigung in zwei Schritten aktiv sein).",
    ),
    MailAnbieter(
        id="icloud", name="iCloud", kuerzel="iC", farbe="#3693F3",
        beschreibung="icloud.com, me.com, mac.com",
        domains=("icloud.com", "me.com", "mac.com"),
        mx_suffixe=(),
        imap_host="imap.mail.me.com", imap_port=993, imap_verschluesselung="ssl",
        smtp_host="smtp.mail.me.com", smtp_port=587, smtp_verschluesselung="starttls",
        hinweis="Ein app-spezifisches Passwort aus dem Apple-Konto verwenden.",
    ),
    MailAnbieter(
        id="posteo", name="Posteo", kuerzel="Po", farbe="#1F6F5C",
        beschreibung="posteo.de, posteo.net",
        domains=("posteo.de", "posteo.net"),
        mx_suffixe=(),
        imap_host="posteo.de", imap_port=993, imap_verschluesselung="ssl",
        smtp_host="posteo.de", smtp_port=587, smtp_verschluesselung="starttls",
    ),
    MailAnbieter(
        id="mailbox_org", name="mailbox.org", kuerzel="mb", farbe="#0E5AA7",
        beschreibung="mailbox.org",
        domains=("mailbox.org",),
        mx_suffixe=(".mailbox.org",),
        imap_host="imap.mailbox.org", imap_port=993, imap_verschluesselung="ssl",
        smtp_host="smtp.mailbox.org", smtp_port=465, smtp_verschluesselung="ssl",
    ),
    MailAnbieter(
        id="hetzner", name="Hetzner", kuerzel="He", farbe="#D50C2D",
        beschreibung="eigene Domain",
        domains=(),
        mx_suffixe=(".your-server.de",),
        imap_host="mail.your-server.de", imap_port=993, imap_verschluesselung="ssl",
        smtp_host="mail.your-server.de", smtp_port=587, smtp_verschluesselung="starttls",
    ),
    # Microsoft hat Basic-Auth für IMAP/SMTP abgeschaltet (nur OAuth), daher in
    # der Liste sichtbar, aber nicht verbindbar.
    MailAnbieter(
        id="microsoft", name="Microsoft 365 / Outlook", kuerzel="MS", farbe="#0078D4",
        beschreibung="outlook.com, hotmail, live, Microsoft 365",
        domains=("outlook.com", "hotmail.com", "hotmail.de", "live.com", "live.de", "msn.com"),
        mx_suffixe=(".mail.protection.outlook.com",),
        imap_host="outlook.office365.com", imap_port=993, imap_verschluesselung="ssl",
        smtp_host="smtp.office365.com", smtp_port=587, smtp_verschluesselung="starttls",
        hinweis="Microsoft erlaubt die Anmeldung per Passwort bei IMAP/SMTP nicht mehr.",
        unterstuetzt=False,
    ),
)

_MX_TIMEOUT_SEKUNDEN = 3


def anbieter_nach_domain(domain: str) -> MailAnbieter | None:
    domain = domain.strip().lower()
    for anbieter in ANBIETER:
        if domain in anbieter.domains:
            return anbieter
    return None


def _anbieter_nach_mx_host(host: str) -> MailAnbieter | None:
    host = host.strip().lower().rstrip(".")
    for anbieter in ANBIETER:
        if any(host.endswith(suffix) for suffix in anbieter.mx_suffixe):
            return anbieter
    return None


async def anbieter_erkennen(email: str) -> tuple[MailAnbieter | None, str | None]:
    """Erst die Domain der Adresse, sonst der Mailserver (MX) der Domain.
    Jeder DNS-Fehler gilt als "nicht erkannt" -- die Erkennung ist nur eine
    Komfortfunktion und darf das Einrichten nie blockieren."""
    _, _, domain = email.strip().lower().rpartition("@")
    if not domain:
        return None, None
    anbieter = anbieter_nach_domain(domain)
    if anbieter is not None:
        return anbieter, "domain"
    try:
        antwort = await dns.asyncresolver.resolve(domain, "MX", lifetime=_MX_TIMEOUT_SEKUNDEN)
        hosts = [str(eintrag.exchange) for eintrag in antwort]
    except Exception:
        return None, None
    for host in hosts:
        anbieter = _anbieter_nach_mx_host(host)
        if anbieter is not None:
            return anbieter, "mx"
    return None, None


def passender_anbieter(account: MailAccount) -> tuple[MailAnbieter | None, bool]:
    imap_host = account.imap_host.lower()
    smtp_host = account.smtp_host.lower()
    for anbieter in ANBIETER:
        if anbieter.imap_host == imap_host or anbieter.smtp_host == smtp_host:
            abweichung = (
                anbieter.imap_host != imap_host
                or anbieter.imap_port != account.imap_port
                or anbieter.imap_verschluesselung != account.imap_verschluesselung
                or anbieter.smtp_host != smtp_host
                or anbieter.smtp_port != account.smtp_port
                or anbieter.smtp_verschluesselung != account.smtp_verschluesselung
            )
            return anbieter, abweichung
    return None, True
