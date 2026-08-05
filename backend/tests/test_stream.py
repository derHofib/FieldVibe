import pytest

from tests.conftest import login


@pytest.mark.asyncio
async def test_stream_requires_token(client):
    resp = await client.get("/api/stream")
    assert resp.status_code == 422  # fehlender Pflicht-Query-Parameter


@pytest.mark.asyncio
async def test_stream_rejects_invalid_token(client):
    resp = await client.get("/api/stream", params={"token": "not-a-real-jwt"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_stream_rejects_super_admin_without_mandant(client, make_user):
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")
    token = await login(client, super_admin.email, "pw-123456")

    resp = await client.get("/api/stream", params={"token": token})
    assert resp.status_code == 403


