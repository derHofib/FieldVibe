from unittest.mock import patch

import pytest

from app.core.config import get_settings
from tests.conftest import auth_headers, login


class _FakeResponse:
    def __init__(self, data: dict):
        self._data = data

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._data


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, *args, **kwargs) -> _FakeResponse:
        return _FakeResponse(
            {
                "sha": "abcdef1234567890",
                "commit": {
                    "message": "Neuestes Feature\n\nLangbeschreibung",
                    "committer": {"date": "2026-08-06T10:00:00Z"},
                },
                "html_url": "https://github.com/derHofib/SocialCRM/commit/abcdef1234567890",
            }
        )


class _FailingAsyncClient(_FakeAsyncClient):
    async def get(self, *args, **kwargs):
        raise ConnectionError("kein Netz")


async def _super_admin_token(client, make_user, email: str) -> str:
    admin = await make_user(mandant=None, role="super_admin", password="admin-pass-1", email=email)
    return await login(client, admin.email, "admin-pass-1")


@pytest.mark.asyncio
async def test_version_zeigt_update_verfuegbar(client, make_user):
    token = await _super_admin_token(client, make_user, "admin-version-1@example.de")
    with patch("app.services.version_service.httpx.AsyncClient", _FakeAsyncClient):
        with patch.object(get_settings(), "git_commit", "0000000"):
            resp = await client.get("/api/admin/version", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["latest_commit_sha"] == "abcdef1"
    assert body["latest_commit_message"] == "Neuestes Feature"
    assert body["update_available"] is True
    assert body["fehler"] is None


@pytest.mark.asyncio
async def test_version_ohne_deployed_commit_zeigt_kein_update_verfuegbar(client, make_user):
    token = await _super_admin_token(client, make_user, "admin-version-2@example.de")
    with patch("app.services.version_service.httpx.AsyncClient", _FakeAsyncClient):
        resp = await client.get("/api/admin/version", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    # Ohne GIT_COMMIT-Build-Arg (Default "unknown") laesst sich kein
    # Update-Status ableiten -- None statt fälschlich False/True.
    assert body["update_available"] is None
    assert body["deployed_commit"] == "unknown"


@pytest.mark.asyncio
async def test_version_meldet_fehler_wenn_github_nicht_erreichbar(client, make_user):
    token = await _super_admin_token(client, make_user, "admin-version-3@example.de")
    with patch("app.services.version_service.httpx.AsyncClient", _FailingAsyncClient):
        resp = await client.get("/api/admin/version", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["fehler"] is not None
    assert body["update_available"] is None


@pytest.mark.asyncio
async def test_mandant_admin_cannot_access_version(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/admin/version", headers=auth_headers(token))
    assert resp.status_code == 403
