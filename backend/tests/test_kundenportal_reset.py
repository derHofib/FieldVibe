import re
from unittest.mock import AsyncMock, patch

import pytest

from app.core.security import create_kundenportal_password_reset_token, hash_password
from app.db.session import system_session
from app.models.integration import MandantIntegration
from app.models.kundenportal import KundenportalZugang
from tests.conftest import auth_headers, login


async def _make_zugang(mandant, kunde, *, email=None, password="alt-passwort-123", aktiv=True):
    async with system_session() as session:
        zugang = KundenportalZugang(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            email=email or f"portal-{kunde.id}@example.de",
            password_hash=hash_password(password),
            name="Kundenportal-Nutzer",
            aktiv=aktiv,
        )
        session.add(zugang)
        await session.flush()
        await session.refresh(zugang)
        return zugang


@pytest.mark.asyncio
async def test_passwort_vergessen_unknown_email_returns_202(client):
    resp = await client.post(
        "/api/kundenportal/auth/passwort-vergessen", json={"email": "nichtvorhanden@example.de"}
    )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_passwort_vergessen_without_smtp_still_returns_202(client, make_mandant, make_kunde):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    await _make_zugang(mandant, kunde, email="ohne-smtp@example.de")

    resp = await client.post(
        "/api/kundenportal/auth/passwort-vergessen", json={"email": "ohne-smtp@example.de"}
    )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_passwort_vergessen_sends_email_and_reset_flow_works(client, make_mandant, make_kunde):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    await _make_zugang(mandant, kunde, email="reset-flow@example.de", password="altes-passwort-123")

    async with system_session() as session:
        session.add(
            MandantIntegration(
                mandant_id=mandant.id,
                typ="smtp",
                config={"host": "smtp.example.de", "from_address": "bot@example.de"},
                aktiv=True,
            )
        )
        await session.commit()

    with patch(
        "app.api.routes.kundenportal_auth.send_email", new_callable=AsyncMock
    ) as mocked_send:
        resp = await client.post(
            "/api/kundenportal/auth/passwort-vergessen", json={"email": "reset-flow@example.de"}
        )
    assert resp.status_code == 202
    mocked_send.assert_called_once()
    _, kwargs = mocked_send.call_args
    assert kwargs["to"] == "reset-flow@example.de"
    match = re.search(r"token=([\w\-.]+)", kwargs["body"])
    assert match is not None
    token = match.group(1)

    reset_resp = await client.post(
        "/api/kundenportal/auth/passwort-zuruecksetzen",
        json={"token": token, "new_password": "brandneues-passwort-456"},
    )
    assert reset_resp.status_code == 204

    old_login = await client.post(
        "/api/kundenportal/auth/login",
        json={"email": "reset-flow@example.de", "password": "altes-passwort-123"},
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/kundenportal/auth/login",
        json={"email": "reset-flow@example.de", "password": "brandneues-passwort-456"},
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_passwort_zuruecksetzen_invalid_token_rejected(client):
    resp = await client.post(
        "/api/kundenportal/auth/passwort-zuruecksetzen",
        json={"token": "kaputter-token", "new_password": "irgendein-passwort-123"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_passwort_zuruecksetzen_too_short_password_rejected(client, make_mandant, make_kunde):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    zugang = await _make_zugang(mandant, kunde, email="kurz-check@example.de")
    token = create_kundenportal_password_reset_token(zugang_id=zugang.id)

    resp = await client.post(
        "/api/kundenportal/auth/passwort-zuruecksetzen",
        json={"token": token, "new_password": "zu-kurz"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_staff_can_set_kunde_password_directly(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    zugang = await _make_zugang(mandant, kunde, email="staff-reset@example.de", password="altes-passwort-123")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/kunden/{kunde.id}/portal-zugaenge/{zugang.id}",
        headers=auth_headers(token),
        json={"password": "vom-mitarbeiter-gesetzt-123"},
    )
    assert resp.status_code == 200

    login_resp = await client.post(
        "/api/kundenportal/auth/login",
        json={"email": "staff-reset@example.de", "password": "vom-mitarbeiter-gesetzt-123"},
    )
    assert login_resp.status_code == 200


@pytest.mark.asyncio
async def test_staff_set_password_too_short_rejected(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    zugang = await _make_zugang(mandant, kunde, email="staff-reset2@example.de")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/kunden/{kunde.id}/portal-zugaenge/{zugang.id}",
        headers=auth_headers(token),
        json={"password": "kurz"},
    )
    assert resp.status_code == 400
