import imaplib
import smtplib
import ssl
from unittest.mock import MagicMock

import pytest

from app.core.config import get_settings
from app.services import mail_netz, mail_service
from app.services.mail_netz import MailVerbindungFehler, pruefe_ziel
from tests.conftest import auth_headers, login
from tests.test_mail_accounts import _KONTO_PAYLOAD, _mock_verbindung_ok


def _dns(monkeypatch, zuordnung: dict[str, list[str]]):
    def fake(host, port):
        if host not in zuordnung:
            raise OSError("Name or service not known")
        return zuordnung[host]

    monkeypatch.setattr(mail_netz, "_aufloesen", fake)


@pytest.mark.parametrize(
    "adresse",
    [
        "127.0.0.1", "10.0.0.5", "172.16.3.4", "192.168.1.1", "169.254.169.254", "0.0.0.0",
        "100.64.0.1", "224.0.0.1", "240.0.0.1", "::1", "fe80::1", "fc00::1", "::", "ff02::1",
        "::ffff:10.0.0.1", "::ffff:127.0.0.1", "::ffff:169.254.169.254",
    ],
)
def test_pruefe_ziel_blockt_nicht_oeffentliche_adressen(monkeypatch, adresse):
    _dns(monkeypatch, {adresse: [adresse]})
    with pytest.raises(MailVerbindungFehler) as exc:
        pruefe_ziel(adresse, 993, "imap")
    assert adresse not in str(exc.value)


def test_pruefe_ziel_blockt_hostname_mit_privater_aufloesung(monkeypatch):
    _dns(monkeypatch, {"intern.example.de": ["10.0.0.7"]})
    with pytest.raises(MailVerbindungFehler):
        pruefe_ziel("intern.example.de", 993, "imap")


def test_pruefe_ziel_blockt_wenn_nur_eine_von_mehreren_adressen_privat_ist(monkeypatch):
    _dns(monkeypatch, {"mix.example.de": ["93.184.216.34", "127.0.0.1"]})
    with pytest.raises(MailVerbindungFehler):
        pruefe_ziel("mix.example.de", 993, "imap")


def test_pruefe_ziel_oeffentliche_ip_ok_und_liefert_ip(monkeypatch):
    _dns(monkeypatch, {"mail.example.de": ["93.184.216.34"]})
    assert pruefe_ziel("mail.example.de", 993, "imap") == "93.184.216.34"


def test_pruefe_ziel_oeffentliche_ipv6_ok(monkeypatch):
    _dns(monkeypatch, {"v6.example.de": ["2606:2800:220:1:248:1893:25c8:1946"]})
    assert pruefe_ziel("v6.example.de", 465, "smtp")


@pytest.mark.parametrize("protokoll,port", [("imap", 25), ("imap", 22), ("smtp", 993), ("smtp", 5432), ("imap", 9000)])
def test_pruefe_ziel_blockt_nicht_erlaubte_ports(monkeypatch, protokoll, port):
    _dns(monkeypatch, {"mail.example.de": ["93.184.216.34"]})
    with pytest.raises(MailVerbindungFehler, match="Port nicht erlaubt"):
        pruefe_ziel("mail.example.de", port, protokoll)


def test_port_allowlist_ist_konfigurierbar(monkeypatch):
    _dns(monkeypatch, {"mail.example.de": ["93.184.216.34"]})
    monkeypatch.setenv("FIELDVIBE_MAIL_ERLAUBTE_SMTP_PORTS", "25,2526")
    get_settings.cache_clear()
    try:
        assert pruefe_ziel("mail.example.de", 2526, "smtp")
    finally:
        monkeypatch.delenv("FIELDVIBE_MAIL_ERLAUBTE_SMTP_PORTS")
        get_settings.cache_clear()


def test_private_hosts_nur_mit_expliziter_einstellung(monkeypatch):
    _dns(monkeypatch, {"localhost": ["127.0.0.1"]})
    monkeypatch.setenv("FIELDVIBE_MAIL_ERLAUBE_PRIVATE_HOSTS", "true")
    get_settings.cache_clear()
    try:
        assert pruefe_ziel("localhost", 143, "imap") == "127.0.0.1"
    finally:
        monkeypatch.delenv("FIELDVIBE_MAIL_ERLAUBE_PRIVATE_HOSTS")
        get_settings.cache_clear()
    with pytest.raises(MailVerbindungFehler):
        pruefe_ziel("localhost", 143, "imap")


def test_nicht_aufloesbarer_host_meldung_ohne_rohtext(monkeypatch):
    _dns(monkeypatch, {})
    with pytest.raises(MailVerbindungFehler) as exc:
        pruefe_ziel("gibtsnicht.example.de", 993, "imap")
    assert str(exc.value) == "Verbindung fehlgeschlagen: Server nicht erreichbar"


def test_ssl_kontext_verifiziert_zertifikat_und_hostname():
    ctx = mail_netz.ssl_kontext()
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_starttls_bei_smtp_und_imap_nutzt_verifizierenden_kontext(monkeypatch):
    _dns(monkeypatch, {"mail.example.de": ["93.184.216.34"]})
    smtp = MagicMock()
    imap = MagicMock()
    monkeypatch.setattr(mail_netz, "_SmtpGepinnt", lambda *a, **k: smtp)
    monkeypatch.setattr(mail_netz, "_ImapGepinnt", lambda *a, **k: imap)

    mail_netz.verbinde_smtp("mail.example.de", 587, "starttls", 5)
    mail_netz.verbinde_imap("mail.example.de", 143, "starttls", 5)

    for ctx in (smtp.starttls.call_args.kwargs["context"], imap.starttls.call_args.kwargs["ssl_context"]):
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True


def test_ssl_varianten_bekommen_verifizierenden_kontext(monkeypatch):
    erfasst = {}

    def fake_smtp_init(self, host, port=0, local_hostname=None, keyfile=None, certfile=None,
                       timeout=None, source_address=None, context=None):
        erfasst["smtp"] = context
        self._host = host

    def fake_imap_init(self, host="", port=993, *args, ssl_context=None, timeout=None, **kw):
        erfasst["imap"] = ssl_context

    monkeypatch.setattr(smtplib.SMTP_SSL, "__init__", fake_smtp_init)
    monkeypatch.setattr(imaplib.IMAP4_SSL, "__init__", fake_imap_init)
    mail_netz._SmtpSslGepinnt("mail.example.de", 465, ip="93.184.216.34", timeout=5)
    mail_netz._ImapSslGepinnt("mail.example.de", 993, ip="93.184.216.34", timeout=5)

    for ctx in erfasst.values():
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True


def test_gepinnter_socket_verbindet_auf_geprueften_ip_und_sni_bleibt_hostname(monkeypatch):
    aufrufe = {}

    def fake_connect(ip, port, timeout):
        aufrufe["ziel"] = (ip, port)
        return "rohsocket"

    class FakeCtx:
        def wrap_socket(self, sock, server_hostname):
            aufrufe["sni"] = server_hostname
            return sock

    monkeypatch.setattr(mail_netz, "_verbinde_socket", fake_connect)
    smtp = mail_netz._SmtpSslGepinnt.__new__(mail_netz._SmtpSslGepinnt)
    smtp._ip, smtp._host, smtp.context = "93.184.216.34", "mail.example.de", FakeCtx()
    smtp._get_socket("mail.example.de", 465, 5)
    assert aufrufe == {"ziel": ("93.184.216.34", 465), "sni": "mail.example.de"}


@pytest.mark.parametrize(
    "fehler,erwartet",
    [
        (ssl.SSLCertVerificationError("certificate verify failed: 10.0.0.5"), "Zertifikat ungültig"),
        (smtplib.SMTPAuthenticationError(535, b"5.7.8 bad credentials for user"), "Anmeldung abgelehnt"),
        (imaplib.IMAP4.error("LOGIN failed: secret banner"), "Anmeldung abgelehnt"),
        (TimeoutError("timed out connecting to 10.1.2.3:993"), "Server nicht erreichbar"),
        (ConnectionRefusedError("[Errno 111] Connection refused 172.18.0.2"), "Server nicht erreichbar"),
    ],
)
def test_uebersetze_fehler_generisch(fehler, erwartet):
    meldung = str(mail_netz.uebersetze_fehler(fehler, "imap"))
    assert meldung == f"Verbindung fehlgeschlagen: {erwartet}"


def test_pruefe_imap_verbindung_gibt_keine_rohdaten_weiter(monkeypatch):
    def boom(*a, **k):
        raise OSError("connect to 10.1.2.3:993 failed, banner: 220 internal-mx")

    monkeypatch.setattr(mail_service, "verbinde_imap", boom)
    with pytest.raises(MailVerbindungFehler) as exc:
        mail_service.pruefe_imap_verbindung(
            mail_service.ImapZugang(host="mail.example.de", port=993, verschluesselung="ssl", benutzername="u", passwort="p")
        )
    assert "10.1.2.3" not in str(exc.value)
    assert "banner" not in str(exc.value)


async def _token(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    return await login(client, user.email, "pw-123456")


@pytest.mark.asyncio
@pytest.mark.parametrize("host", ["127.0.0.1", "169.254.169.254", "10.0.0.5", "[::1]", "::ffff:192.168.0.1"])
async def test_route_test_verbindung_blockt_private_ziele(client, make_mandant, make_user, monkeypatch, host):
    _dns(monkeypatch, {host: [host.strip("[]")]})
    token = await _token(client, make_mandant, make_user)
    body = {k: v for k, v in _KONTO_PAYLOAD.items() if k not in ("name", "email_adresse", "signatur")}
    body["imap_host"] = host
    resp = await client.post("/api/mail-accounts/test-verbindung", headers=auth_headers(token), json=body)
    assert resp.status_code == 400
    assert host not in resp.json()["detail"]


@pytest.mark.asyncio
async def test_route_create_blockt_hostname_mit_privater_aufloesung(client, make_mandant, make_user, monkeypatch):
    _dns(monkeypatch, {"imap.example.de": ["10.0.0.9"], "smtp.example.de": ["93.184.216.34"]})
    token = await _token(client, make_mandant, make_user)
    resp = await client.post("/api/mail-accounts", headers=auth_headers(token), json=_KONTO_PAYLOAD)
    assert resp.status_code == 400
    assert "10.0.0.9" not in resp.text


@pytest.mark.asyncio
async def test_route_create_blockt_nicht_erlaubten_port(client, make_mandant, make_user):
    token = await _token(client, make_mandant, make_user)
    resp = await client.post(
        "/api/mail-accounts", headers=auth_headers(token), json={**_KONTO_PAYLOAD, "smtp_port": 5432}
    )
    assert resp.status_code == 400
    assert "Port" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_route_patch_host_aenderung_auf_private_ip_wird_geblockt(client, make_mandant, make_user, monkeypatch):
    _mock_verbindung_ok(monkeypatch)
    token = await _token(client, make_mandant, make_user)
    angelegt = await client.post("/api/mail-accounts", headers=auth_headers(token), json=_KONTO_PAYLOAD)
    assert angelegt.status_code == 201
    _dns(monkeypatch, {"intern.example.de": ["192.168.0.10"]})
    resp = await client.patch(
        f"/api/mail-accounts/{angelegt.json()['id']}", headers=auth_headers(token), json={"imap_host": "intern.example.de"}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_route_oeffentliche_ip_wird_akzeptiert(client, make_mandant, make_user, monkeypatch):
    _mock_verbindung_ok(monkeypatch)
    token = await _token(client, make_mandant, make_user)
    resp = await client.post("/api/mail-accounts", headers=auth_headers(token), json=_KONTO_PAYLOAD)
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_route_fehlermeldung_enthaelt_keine_rohdaten(client, make_mandant, make_user, monkeypatch):
    def boom(*a, **k):
        raise OSError("connect to 10.1.2.3:993 failed, banner: 220 internal-mx")

    monkeypatch.setattr(mail_service, "verbinde_imap", boom)
    token = await _token(client, make_mandant, make_user)
    body = {k: v for k, v in _KONTO_PAYLOAD.items() if k not in ("name", "email_adresse", "signatur")}
    resp = await client.post("/api/mail-accounts/test-verbindung", headers=auth_headers(token), json=body)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Verbindung fehlgeschlagen: Server nicht erreichbar"


@pytest.mark.parametrize("verbinde", [mail_netz.verbinde_imap, mail_netz.verbinde_smtp])
def test_klartext_verbindung_wird_abgelehnt_bevor_verbunden_wird(monkeypatch, verbinde):
    def _nie(*a, **k):
        raise AssertionError("darf nicht verbinden")

    monkeypatch.setattr(mail_netz, "_verbinde_socket", _nie)
    port = 143 if verbinde is mail_netz.verbinde_imap else 25
    with pytest.raises(MailVerbindungFehler) as exc:
        verbinde("mail.example.de", port, "keine", 5)
    assert str(exc.value) == mail_netz.UNVERSCHLUESSELT_FEHLER


def test_klartext_nur_mit_private_hosts_einstellung_erlaubt(monkeypatch):
    monkeypatch.setenv("FIELDVIBE_MAIL_ERLAUBE_PRIVATE_HOSTS", "true")
    get_settings.cache_clear()
    try:
        assert mail_netz.klartext_erlaubt() is True
    finally:
        monkeypatch.delenv("FIELDVIBE_MAIL_ERLAUBE_PRIVATE_HOSTS")
        get_settings.cache_clear()
    assert mail_netz.klartext_erlaubt() is False
