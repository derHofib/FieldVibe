import pytest

from app.core.security import decrypt_secret
from app.db.session import system_session
from app.models.integration import MandantIntegration
from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_admin_can_create_smtp_integration_with_encrypted_secret(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/integrationen",
        headers=auth_headers(token),
        json={
            "typ": "smtp",
            "config": {"host": "smtp.example.de", "port": 587, "user": "bot@example.de", "from_address": "bot@example.de"},
            "secret": "super-geheimes-passwort",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["typ"] == "smtp"
    assert body["hat_secret"] is True
    assert "secret" not in body
    integration_id = body["id"]

    async with system_session() as session:
        row = await session.get(MandantIntegration, integration_id)
        assert row.secret_ref != "super-geheimes-passwort"
        assert decrypt_secret(row.secret_ref) == "super-geheimes-passwort"


@pytest.mark.asyncio
async def test_unknown_typ_rejected(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/integrationen", headers=auth_headers(token), json={"typ": "lexoffice"}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_non_admin_cannot_manage_integrationen(client, make_mandant, make_user):
    mandant = await make_mandant()
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    token = await login(client, disponent.email, "pw-123456")

    resp = await client.post("/api/integrationen", headers=auth_headers(token), json={"typ": "smtp"})
    assert resp.status_code == 403

    list_resp = await client.get("/api/integrationen", headers=auth_headers(token))
    assert list_resp.status_code == 403


@pytest.mark.asyncio
async def test_update_config_without_secret_leaves_secret_untouched(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    created = await client.post(
        "/api/integrationen",
        headers=auth_headers(token),
        json={"typ": "smtp", "config": {"host": "a"}, "secret": "geheim"},
    )
    integration_id = created.json()["id"]

    updated = await client.patch(
        f"/api/integrationen/{integration_id}",
        headers=auth_headers(token),
        json={"config": {"host": "b"}},
    )
    assert updated.status_code == 200
    assert updated.json()["config"] == {"host": "b"}
    assert updated.json()["hat_secret"] is True

    async with system_session() as session:
        row = await session.get(MandantIntegration, integration_id)
        assert decrypt_secret(row.secret_ref) == "geheim"


@pytest.mark.asyncio
async def test_update_can_explicitly_clear_secret(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    created = await client.post(
        "/api/integrationen", headers=auth_headers(token), json={"typ": "smtp", "secret": "geheim"}
    )
    integration_id = created.json()["id"]

    updated = await client.patch(
        f"/api/integrationen/{integration_id}", headers=auth_headers(token), json={"secret": None}
    )
    assert updated.status_code == 200
    assert updated.json()["hat_secret"] is False


@pytest.mark.asyncio
async def test_delete_integration(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    created = await client.post("/api/integrationen", headers=auth_headers(token), json={"typ": "smtp"})
    integration_id = created.json()["id"]

    resp = await client.delete(f"/api/integrationen/{integration_id}", headers=auth_headers(token))
    assert resp.status_code == 204

    list_resp = await client.get("/api/integrationen", headers=auth_headers(token))
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_mandant_isolation_for_integrationen(client, make_mandant, make_user):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    admin1 = await make_user(mandant=mandant1, role="mandant_admin", password="pw-123456")
    admin2 = await make_user(mandant=mandant2, role="mandant_admin", password="pw-123456")
    token1 = await login(client, admin1.email, "pw-123456")
    token2 = await login(client, admin2.email, "pw-123456")

    created = await client.post("/api/integrationen", headers=auth_headers(token1), json={"typ": "smtp"})
    assert created.status_code == 201

    list_resp = await client.get("/api/integrationen", headers=auth_headers(token2))
    assert list_resp.json() == []
