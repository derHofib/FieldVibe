from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import STREAM_TICKET_SEKUNDEN, decode_token
from tests.conftest import auth_headers, login

_settings = get_settings()


async def _ticket(client, token):
    resp = await client.post("/api/stream/ticket", headers=auth_headers(token))
    assert resp.status_code == 200
    return resp.json()


@pytest.mark.asyncio
async def test_stream_requires_ticket(client):
    resp = await client.get("/api/stream")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_stream_rejects_invalid_ticket(client):
    resp = await client.get("/api/stream", params={"ticket": "not-a-real-jwt"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_stream_rejects_access_token_in_query(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    # Weder als altes ?token= noch als ?ticket= taugt ein Access-Token.
    assert (await client.get("/api/stream", params={"token": token})).status_code == 401
    assert (await client.get("/api/stream", params={"ticket": token})).status_code == 401


@pytest.mark.asyncio
async def test_ticket_requires_authentication_and_is_not_a_bearer_token(client, make_mandant, make_user):
    assert (await client.post("/api/stream/ticket")).status_code == 401

    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    ticket = (await _ticket(client, token))["ticket"]

    # Ticket-Typ "stream" ist kein API-Token.
    assert (await client.get("/api/auth/me", headers=auth_headers(ticket))).status_code == 401
    assert (await client.post("/api/stream/ticket", headers=auth_headers(ticket))).status_code == 401


@pytest.mark.asyncio
async def test_ticket_contents(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    daten = await _ticket(client, token)
    payload = decode_token(daten["ticket"])
    assert payload["type"] == "stream"
    assert payload["sub"] == str(admin.id)
    assert payload["mandant_id"] == str(mandant.id)
    assert payload["tv"] == 0
    assert payload["jti"]
    assert payload["exp"] - payload["iat"] == STREAM_TICKET_SEKUNDEN
    gueltig_bis = datetime.fromisoformat(daten["gueltig_bis"])
    assert timedelta(seconds=50) < gueltig_bis - datetime.now(timezone.utc) <= timedelta(seconds=61)


@pytest.mark.asyncio
async def test_ticket_rejected_for_super_admin_without_mandant(client, make_user):
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")
    token = await login(client, super_admin.email, "pw-123456")

    resp = await client.post("/api/stream/ticket", headers=auth_headers(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_stream_rejects_expired_ticket(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    jetzt = datetime.now(timezone.utc)
    abgelaufen = jwt.encode(
        {
            "sub": str(admin.id),
            "role": "mandant_admin",
            "mandant_id": str(mandant.id),
            "type": "stream",
            "tv": 0,
            "jti": uuid4().hex,
            "iat": jetzt - timedelta(minutes=5),
            "exp": jetzt - timedelta(minutes=4),
        },
        _settings.jwt_secret,
        algorithm=_settings.jwt_algorithm,
    )
    resp = await client.get("/api/stream", params={"ticket": abgelaufen})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_stream_rejects_refresh_token_as_ticket(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    resp = await client.post("/api/auth/login", json={"email": admin.email, "password": "pw-123456"})
    refresh = resp.json()["refresh_token"]

    assert (await client.get("/api/stream", params={"ticket": refresh})).status_code == 401


@pytest.mark.asyncio
async def test_stream_ticket_invalid_after_token_version_change(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    ticket = (await _ticket(client, token))["ticket"]

    resp = await client.post("/api/auth/ueberall-abmelden", headers=auth_headers(token))
    assert resp.status_code == 204

    assert (await client.get("/api/stream", params={"ticket": ticket})).status_code == 401


@pytest.mark.asyncio
async def test_valid_ticket_is_accepted(client, make_mandant, make_user):
    from unittest.mock import MagicMock

    from app.api.routes.stream import stream

    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    ticket = (await _ticket(client, token))["ticket"]

    # Direkter Aufruf: ein echter SSE-Request wuerde ueber ASGITransport nie enden.
    antwort = await stream(MagicMock(), ticket=ticket)
    assert antwort.status_code == 200


@pytest.mark.asyncio
async def test_ticket_ohne_tv_ungueltig(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    jetzt = datetime.now(timezone.utc)
    ticket = jwt.encode(
        {
            "sub": str(admin.id),
            "role": "mandant_admin",
            "mandant_id": str(mandant.id),
            "type": "stream",
            "jti": uuid4().hex,
            "iat": jetzt,
            "exp": jetzt + timedelta(seconds=60),
        },
        _settings.jwt_secret,
        algorithm=_settings.jwt_algorithm,
    )
    assert (await client.get("/api/stream", params={"ticket": ticket})).status_code == 401


@pytest.mark.asyncio
async def test_offene_verbindung_endet_nach_widerruf(client, make_mandant, make_user, monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from app.api.routes import stream as stream_modul

    monkeypatch.setattr(stream_modul, "_PRUEFINTERVALL_SEKUNDEN", 0)
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    ticket = (await _ticket(client, token))["ticket"]

    request = MagicMock()
    request.is_disconnected = AsyncMock(return_value=False)
    antwort = await stream_modul.stream(request, ticket=ticket)

    assert (await client.post("/api/auth/ueberall-abmelden", headers=auth_headers(token))).status_code == 204
    # Generator muss von selbst enden (sonst haengt der Test).
    import asyncio

    async def leeren():
        async for _ in antwort.body_iterator:
            pass

    await asyncio.wait_for(leeren(), timeout=5)
