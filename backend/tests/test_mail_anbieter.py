import dns.exception
import dns.resolver
import pytest

from app.core.security import encrypt_secret
from app.db.session import system_session
from app.models.mail_account import MailAccount
from app.models.mail_folder import MailFolder
from app.models.mail_message import MailMessage
from app.services import mail_anbieter
from tests.conftest import auth_headers, login


class _MxEintrag:
    def __init__(self, host: str):
        self.exchange = host


def _mock_mx(monkeypatch, *, hosts=None, fehler=None):
    aufrufe = []

    async def _resolve(domain, rdtype, **kwargs):
        aufrufe.append((domain, rdtype, kwargs))
        if fehler is not None:
            raise fehler
        return [_MxEintrag(h) for h in hosts]

    monkeypatch.setattr(mail_anbieter.dns.asyncresolver, "resolve", _resolve)
    return aufrufe


@pytest.mark.asyncio
async def test_erkennung_nach_domain_ohne_dns(monkeypatch):
    aufrufe = _mock_mx(monkeypatch, fehler=AssertionError("kein DNS erwartet"))
    anbieter, quelle = await mail_anbieter.anbieter_erkennen("Max@GMX.net")
    assert anbieter.id == "gmx"
    assert quelle == "domain"
    assert aufrufe == []


@pytest.mark.asyncio
async def test_erkennung_nach_mx(monkeypatch):
    aufrufe = _mock_mx(monkeypatch, hosts=["mx00.IONOS.de."])
    anbieter, quelle = await mail_anbieter.anbieter_erkennen("info@hofion.de")
    assert anbieter.id == "ionos"
    assert quelle == "mx"
    assert aufrufe[0][2]["lifetime"] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("fehler", [dns.resolver.NXDOMAIN(), dns.exception.Timeout(), RuntimeError("x")])
async def test_dns_fehler_ergeben_nicht_erkannt(monkeypatch, fehler):
    _mock_mx(monkeypatch, fehler=fehler)
    assert await mail_anbieter.anbieter_erkennen("info@unbekannt.example") == (None, None)


@pytest.mark.asyncio
async def test_unbekannter_mx_ergibt_nicht_erkannt(monkeypatch):
    _mock_mx(monkeypatch, hosts=["mail.irgendwer.example."])
    assert await mail_anbieter.anbieter_erkennen("info@firma.example") == (None, None)


def _konto(**ueberschreibungen) -> MailAccount:
    werte = dict(
        name="K", email_adresse="a@b.de",
        imap_host="imap.ionos.de", imap_port=993, imap_verschluesselung="ssl", imap_benutzername="a@b.de",
        smtp_host="smtp.ionos.de", smtp_port=587, smtp_verschluesselung="starttls", smtp_benutzername="a@b.de",
    )
    werte.update(ueberschreibungen)
    return MailAccount(**werte)


def test_passender_anbieter_vorgabe_unveraendert():
    anbieter, angepasst = mail_anbieter.passender_anbieter(_konto(imap_host="IMAP.ionos.de"))
    assert anbieter.id == "ionos"
    assert angepasst is False


def test_passender_anbieter_smtp_port_abweichend():
    anbieter, angepasst = mail_anbieter.passender_anbieter(_konto(smtp_port=465, smtp_verschluesselung="ssl"))
    assert anbieter.id == "ionos"
    assert angepasst is True


def test_passender_anbieter_unbekannter_host():
    anbieter, angepasst = mail_anbieter.passender_anbieter(
        _konto(imap_host="imap.example.de", smtp_host="smtp.example.de")
    )
    assert anbieter is None
    assert angepasst is True


async def _login(client, make_mandant, make_user, **mandant_kwargs):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    return mandant, user, await login(client, user.email, "pw-123456")


@pytest.mark.asyncio
async def test_anbieterliste(client, make_mandant, make_user):
    _, _, token = await _login(client, make_mandant, make_user)
    resp = await client.get("/api/mail-accounts/anbieter", headers=auth_headers(token))
    assert resp.status_code == 200
    liste = resp.json()
    nach_id = {a["id"]: a for a in liste}
    assert liste[0]["id"] == "ionos"
    assert nach_id["ionos"]["imap_host"] == "imap.ionos.de"
    assert nach_id["ionos"]["unterstuetzt"] is True
    assert nach_id["microsoft"]["unterstuetzt"] is False
    assert "mx_suffixe" not in nach_id["ionos"]


@pytest.mark.asyncio
async def test_erkennen_endpunkt(client, make_mandant, make_user, monkeypatch):
    _mock_mx(monkeypatch, hosts=["mx00.ionos.de."])
    _, _, token = await _login(client, make_mandant, make_user)
    resp = await client.post(
        "/api/mail-accounts/anbieter-erkennen", headers=auth_headers(token), json={"email_adresse": "info@hofion.de"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["quelle"] == "mx"
    assert body["anbieter"]["id"] == "ionos"

    _mock_mx(monkeypatch, fehler=dns.exception.Timeout())
    resp = await client.post(
        "/api/mail-accounts/anbieter-erkennen", headers=auth_headers(token), json={"email_adresse": "info@x.example"}
    )
    assert resp.json() == {"anbieter": None, "quelle": None}


@pytest.mark.asyncio
async def test_erkennen_ohne_login_401(client):
    resp = await client.post("/api/mail-accounts/anbieter-erkennen", json={"email_adresse": "a@gmx.de"})
    assert resp.status_code == 401
    assert (await client.get("/api/mail-accounts/anbieter")).status_code == 401


@pytest.mark.asyncio
async def test_ohne_modul_postfach_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    async with system_session(grund="test") as session:
        m = await session.get(type(mandant), mandant.id)
        m.deaktivierte_module = ["postfach"]
    token = await login(client, user.email, "pw-123456")
    assert (await client.get("/api/mail-accounts/anbieter", headers=auth_headers(token))).status_code == 403
    resp = await client.post(
        "/api/mail-accounts/anbieter-erkennen", headers=auth_headers(token), json={"email_adresse": "a@gmx.de"}
    )
    assert resp.status_code == 403


async def _konto_anlegen(mandant, user, **ueberschreibungen) -> MailAccount:
    werte = dict(
        mandant_id=mandant.id, user_id=user.id, passwort_verschluesselt=encrypt_secret("geheim"),
        name="K", email_adresse="technik@example.de",
        imap_host="imap.ionos.de", imap_port=993, imap_verschluesselung="ssl", imap_benutzername="technik@example.de",
        smtp_host="smtp.ionos.de", smtp_port=587, smtp_verschluesselung="starttls",
        smtp_benutzername="technik@example.de",
    )
    werte.update(ueberschreibungen)
    async with system_session(grund="test") as session:
        konto = MailAccount(**werte)
        session.add(konto)
        await session.flush()
        await session.refresh(konto)
        return konto


@pytest.mark.asyncio
async def test_account_read_anbieter_und_angepasst(client, make_mandant, make_user):
    mandant, user, token = await _login(client, make_mandant, make_user)
    await _konto_anlegen(mandant, user)
    await _konto_anlegen(
        mandant, user, email_adresse="b@example.de", name="B", smtp_port=465, smtp_verschluesselung="ssl"
    )
    await _konto_anlegen(
        mandant, user, email_adresse="c@example.de", name="C", imap_host="imap.example.de", smtp_host="smtp.example.de"
    )
    resp = await client.get("/api/mail-accounts", headers=auth_headers(token))
    nach_name = {k["name"]: k for k in resp.json()}
    assert (nach_name["K"]["anbieter_id"], nach_name["K"]["server_angepasst"]) == ("ionos", False)
    assert (nach_name["B"]["anbieter_id"], nach_name["B"]["server_angepasst"]) == ("ionos", True)
    assert (nach_name["C"]["anbieter_id"], nach_name["C"]["server_angepasst"]) == (None, True)


@pytest.mark.asyncio
async def test_ordner_ungelesen_zaehlung(client, make_mandant, make_user):
    mandant, user, token = await _login(client, make_mandant, make_user)
    konto = await _konto_anlegen(mandant, user)
    async with system_session(grund="test") as session:
        ordner = []
        for name in ("INBOX", "Sent"):
            o = MailFolder(
                mandant_id=mandant.id, mail_account_id=konto.id, imap_name=name, anzeigename=name,
                uidvalidity=1, last_uid=0,
            )
            session.add(o)
            ordner.append(o)
        await session.flush()
        for uid, (o, gelesen) in enumerate([(ordner[0], False), (ordner[0], False), (ordner[0], True)], start=1):
            session.add(
                MailMessage(
                    mandant_id=mandant.id, mail_account_id=konto.id, folder_id=o.id, uid=uid,
                    von_adresse="k@example.de", an=[], cc=[], betreff="b", body_text="t",
                    gelesen=gelesen, message_id_header=f"<{uid}@example.de>",
                )
            )
    resp = await client.get(f"/api/mail-accounts/{konto.id}/folders", headers=auth_headers(token))
    assert resp.status_code == 200
    zahlen = {o["imap_name"]: o["ungelesen"] for o in resp.json()}
    assert zahlen == {"INBOX": 2, "Sent": 0}

    user2 = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token2 = await login(client, user2.email, "pw-123456")
    resp = await client.get(f"/api/mail-accounts/{konto.id}/folders", headers=auth_headers(token2))
    assert resp.status_code == 404
