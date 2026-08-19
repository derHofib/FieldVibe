import pytest

from app.core.security import decrypt_secret
from app.db.session import system_session
from app.models.mail_account import MailAccount
from app.services.mail_service import MailVerbindungFehler
from tests.conftest import auth_headers, login

_KONTO_PAYLOAD = {
    "name": "Mein Postfach",
    "email_adresse": "technik@example.de",
    "imap_host": "imap.example.de",
    "imap_port": 993,
    "imap_verschluesselung": "ssl",
    "imap_benutzername": "technik@example.de",
    "smtp_host": "smtp.example.de",
    "smtp_port": 587,
    "smtp_verschluesselung": "starttls",
    "smtp_benutzername": "technik@example.de",
    "passwort": "super-geheim",
}


def _mock_verbindung_ok(monkeypatch):
    monkeypatch.setattr("app.api.routes.mail_accounts.pruefe_imap_verbindung", lambda zugang: None)
    monkeypatch.setattr("app.api.routes.mail_accounts.pruefe_smtp_verbindung", lambda zugang: None)


def _mock_verbindung_fehler(monkeypatch):
    def _fail(zugang):
        raise MailVerbindungFehler("IMAP-Anmeldung fehlgeschlagen: falsches Passwort")

    monkeypatch.setattr("app.api.routes.mail_accounts.pruefe_imap_verbindung", _fail)
    monkeypatch.setattr("app.api.routes.mail_accounts.pruefe_smtp_verbindung", lambda zugang: None)


@pytest.mark.asyncio
async def test_create_mail_account_verschluesselt_passwort_und_gibt_es_nie_zurueck(
    client, make_mandant, make_user, monkeypatch
):
    _mock_verbindung_ok(monkeypatch)
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, user.email, "pw-123456")

    resp = await client.post("/api/mail-accounts", headers=auth_headers(token), json=_KONTO_PAYLOAD)
    assert resp.status_code == 201
    body = resp.json()
    assert body["email_adresse"] == "technik@example.de"
    assert "passwort" not in body
    assert "passwort_verschluesselt" not in body

    async with system_session() as session:
        row = await session.get(MailAccount, body["id"])
        assert row.passwort_verschluesselt != "super-geheim"
        assert decrypt_secret(row.passwort_verschluesselt) == "super-geheim"


@pytest.mark.asyncio
async def test_create_mail_account_scheitert_verbindungstest_legt_nichts_an(
    client, make_mandant, make_user, monkeypatch
):
    _mock_verbindung_fehler(monkeypatch)
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, user.email, "pw-123456")

    resp = await client.post("/api/mail-accounts", headers=auth_headers(token), json=_KONTO_PAYLOAD)
    assert resp.status_code == 400

    list_resp = await client.get("/api/mail-accounts", headers=auth_headers(token))
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_test_verbindung_endpoint_ohne_speichern(client, make_mandant, make_user, monkeypatch):
    _mock_verbindung_ok(monkeypatch)
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, user.email, "pw-123456")

    resp = await client.post(
        "/api/mail-accounts/test-verbindung",
        headers=auth_headers(token),
        json={k: v for k, v in _KONTO_PAYLOAD.items() if k not in ("name", "email_adresse")},
    )
    assert resp.status_code == 204

    list_resp = await client.get("/api/mail-accounts", headers=auth_headers(token))
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_user_sieht_nur_eigenes_postfach(client, make_mandant, make_user, monkeypatch):
    _mock_verbindung_ok(monkeypatch)
    mandant = await make_mandant()
    user1 = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    user2 = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token1 = await login(client, user1.email, "pw-123456")
    token2 = await login(client, user2.email, "pw-123456")

    created = await client.post("/api/mail-accounts", headers=auth_headers(token1), json=_KONTO_PAYLOAD)
    assert created.status_code == 201

    list1 = await client.get("/api/mail-accounts", headers=auth_headers(token1))
    assert len(list1.json()) == 1

    list2 = await client.get("/api/mail-accounts", headers=auth_headers(token2))
    assert list2.json() == []

    # Auch ueber die ID direkt darf user2 nicht an user1s Konto heran.
    account_id = created.json()["id"]
    patch_resp = await client.patch(
        f"/api/mail-accounts/{account_id}", headers=auth_headers(token2), json={"name": "Uebernommen"}
    )
    assert patch_resp.status_code == 404

    delete_resp = await client.delete(f"/api/mail-accounts/{account_id}", headers=auth_headers(token2))
    assert delete_resp.status_code == 404


@pytest.mark.asyncio
async def test_mandant_isolation_fuer_mail_accounts(client, make_mandant, make_user, monkeypatch):
    _mock_verbindung_ok(monkeypatch)
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    user1 = await make_user(mandant=mandant1, role="techniker", password="pw-123456")
    user2 = await make_user(mandant=mandant2, role="techniker", password="pw-123456")
    token1 = await login(client, user1.email, "pw-123456")
    token2 = await login(client, user2.email, "pw-123456")

    created = await client.post("/api/mail-accounts", headers=auth_headers(token1), json=_KONTO_PAYLOAD)
    assert created.status_code == 201

    list2 = await client.get("/api/mail-accounts", headers=auth_headers(token2))
    assert list2.json() == []


@pytest.mark.asyncio
async def test_update_ohne_passwort_laesst_gespeichertes_passwort_unveraendert(
    client, make_mandant, make_user, monkeypatch
):
    _mock_verbindung_ok(monkeypatch)
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, user.email, "pw-123456")

    created = await client.post("/api/mail-accounts", headers=auth_headers(token), json=_KONTO_PAYLOAD)
    account_id = created.json()["id"]

    updated = await client.patch(
        f"/api/mail-accounts/{account_id}", headers=auth_headers(token), json={"signatur": "Mit freundlichen Grüßen"}
    )
    assert updated.status_code == 200
    assert updated.json()["signatur"] == "Mit freundlichen Grüßen"

    async with system_session() as session:
        row = await session.get(MailAccount, account_id)
        assert decrypt_secret(row.passwort_verschluesselt) == "super-geheim"


@pytest.mark.asyncio
async def test_update_mit_neuem_passwort_prueft_verbindung_erneut_und_verschluesselt_neu(
    client, make_mandant, make_user, monkeypatch
):
    _mock_verbindung_ok(monkeypatch)
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, user.email, "pw-123456")

    created = await client.post("/api/mail-accounts", headers=auth_headers(token), json=_KONTO_PAYLOAD)
    account_id = created.json()["id"]

    updated = await client.patch(
        f"/api/mail-accounts/{account_id}", headers=auth_headers(token), json={"passwort": "neues-passwort"}
    )
    assert updated.status_code == 200

    async with system_session() as session:
        row = await session.get(MailAccount, account_id)
        assert decrypt_secret(row.passwort_verschluesselt) == "neues-passwort"


@pytest.mark.asyncio
async def test_update_mit_falschem_neuem_passwort_wird_abgelehnt(
    client, make_mandant, make_user, monkeypatch
):
    _mock_verbindung_ok(monkeypatch)
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, user.email, "pw-123456")

    created = await client.post("/api/mail-accounts", headers=auth_headers(token), json=_KONTO_PAYLOAD)
    account_id = created.json()["id"]

    _mock_verbindung_fehler(monkeypatch)
    updated = await client.patch(
        f"/api/mail-accounts/{account_id}", headers=auth_headers(token), json={"passwort": "falsch"}
    )
    assert updated.status_code == 400

    async with system_session() as session:
        row = await session.get(MailAccount, account_id)
        assert decrypt_secret(row.passwort_verschluesselt) == "super-geheim"


@pytest.mark.asyncio
async def test_delete_mail_account(client, make_mandant, make_user, monkeypatch):
    _mock_verbindung_ok(monkeypatch)
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, user.email, "pw-123456")

    created = await client.post("/api/mail-accounts", headers=auth_headers(token), json=_KONTO_PAYLOAD)
    account_id = created.json()["id"]

    resp = await client.delete(f"/api/mail-accounts/{account_id}", headers=auth_headers(token))
    assert resp.status_code == 204

    list_resp = await client.get("/api/mail-accounts", headers=auth_headers(token))
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_doppelte_email_adresse_fuer_denselben_nutzer_wird_abgelehnt(
    client, make_mandant, make_user, monkeypatch
):
    _mock_verbindung_ok(monkeypatch)
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, user.email, "pw-123456")

    first = await client.post("/api/mail-accounts", headers=auth_headers(token), json=_KONTO_PAYLOAD)
    assert first.status_code == 201

    second = await client.post("/api/mail-accounts", headers=auth_headers(token), json=_KONTO_PAYLOAD)
    assert second.status_code == 409
