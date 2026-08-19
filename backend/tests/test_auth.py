import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_login_success(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", password="korrekt-123")

    resp = await client.post(
        "/api/auth/login", json={"email": user.email, "password": "korrekt-123"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body


@pytest.mark.asyncio
async def test_login_ignores_email_case(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(
        mandant=mandant, role="mandant_admin", password="korrekt-123", email="Dennis@FieldVibe.de"
    )

    resp = await client.post(
        "/api/auth/login", json={"email": "dennis@fieldvibe.de", "password": "korrekt-123"}
    )
    assert resp.status_code == 200

    resp2 = await client.post(
        "/api/auth/login", json={"email": "DENNIS@FIELDVIBE.DE", "password": "korrekt-123"}
    )
    assert resp2.status_code == 200
    assert resp2.json()["access_token"]
    assert user.email == "Dennis@FieldVibe.de"


@pytest.mark.asyncio
async def test_einladung_normalizes_email_case(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/users/einladungen",
        headers=auth_headers(token),
        json={"email": "Neuer.Techniker@Firma.DE", "role": "mandant_admin"},
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == "neuer.techniker@firma.de"


@pytest.mark.asyncio
async def test_login_wrong_password(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="korrekt-123")

    resp = await client.post(
        "/api/auth/login", json={"email": user.email, "password": "falsch"}
    )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email(client):
    resp = await client.post(
        "/api/auth/login",
        json={"email": "nobody@example.de", "password": "irrelevant"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_deactivated_user_rejected(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(
        mandant=mandant, role="techniker", password="korrekt-123", aktiv=False
    )

    resp = await client.post(
        "/api/auth/login", json={"email": user.email, "password": "korrekt-123"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_login_rejected_for_paused_mandant(client, make_mandant, make_user):
    mandant = await make_mandant(status="pausiert")
    user = await make_user(mandant=mandant, role="techniker", password="korrekt-123")

    resp = await client.post(
        "/api/auth/login", json={"email": user.email, "password": "korrekt-123"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_me_returns_profile(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", password="korrekt-123")
    token = await login(client, user.email, "korrekt-123")

    resp = await client.get("/api/auth/me", headers=auth_headers(token))

    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == user.email
    assert body["mandant_id"] == str(mandant.id)
    assert body["mandant_name"] == mandant.name
    assert body["impersonated_by"] is None


@pytest.mark.asyncio
async def test_me_requires_token(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_issues_new_pair(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="korrekt-123")

    login_resp = await client.post(
        "/api/auth/login", json={"email": user.email, "password": "korrekt-123"}
    )
    refresh_token = login_resp.json()["refresh_token"]

    resp = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})

    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_refresh_rejects_access_token(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="techniker", password="korrekt-123")
    access_token = await login(client, user.email, "korrekt-123")

    resp = await client.post(
        "/api/auth/refresh", json={"refresh_token": access_token}
    )
    assert resp.status_code == 401
