import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_super_admin_can_create_and_list_mandanten(client, make_user):
    admin = await make_user(mandant=None, role="super_admin", password="admin-pass-1")
    token = await login(client, admin.email, "admin-pass-1")

    create_resp = await client.post(
        "/api/admin/mandanten",
        headers=auth_headers(token),
        json={"name": "Elektro Mueller", "slug": "elektro-mueller"},
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["status"] == "aktiv"

    list_resp = await client.get("/api/admin/mandanten", headers=auth_headers(token))
    assert list_resp.status_code == 200
    assert any(m["slug"] == "elektro-mueller" for m in list_resp.json())


@pytest.mark.asyncio
async def test_duplicate_slug_conflicts(client, make_user):
    admin = await make_user(mandant=None, role="super_admin", password="admin-pass-1")
    token = await login(client, admin.email, "admin-pass-1")

    payload = {"name": "Elektro A", "slug": "elektro-dup"}
    first = await client.post(
        "/api/admin/mandanten", headers=auth_headers(token), json=payload
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/admin/mandanten",
        headers=auth_headers(token),
        json={"name": "Elektro B", "slug": "elektro-dup"},
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_mandant_admin_cannot_manage_mandanten(client, make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, user.email, "pw-123456")

    resp = await client.get("/api/admin/mandanten", headers=auth_headers(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_super_admin_can_update_mandant_status(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=None, role="super_admin", password="admin-pass-1")
    token = await login(client, admin.email, "admin-pass-1")

    resp = await client.patch(
        f"/api/admin/mandanten/{mandant.id}",
        headers=auth_headers(token),
        json={"status": "pausiert"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "pausiert"


@pytest.mark.asyncio
async def test_super_admin_can_set_deaktivierte_module(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=None, role="super_admin", password="admin-pass-1")
    token = await login(client, admin.email, "admin-pass-1")

    resp = await client.patch(
        f"/api/admin/mandanten/{mandant.id}",
        headers=auth_headers(token),
        json={"deaktivierte_module": ["material", "dispo"]},
    )
    assert resp.status_code == 200
    assert sorted(resp.json()["deaktivierte_module"]) == ["dispo", "material"]


@pytest.mark.asyncio
async def test_unbekanntes_modul_wird_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=None, role="super_admin", password="admin-pass-1")
    token = await login(client, admin.email, "admin-pass-1")

    resp = await client.patch(
        f"/api/admin/mandanten/{mandant.id}",
        headers=auth_headers(token),
        json={"deaktivierte_module": ["nonexistent"]},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unknown_mandant_returns_404(client, make_user):
    admin = await make_user(mandant=None, role="super_admin", password="admin-pass-1")
    token = await login(client, admin.email, "admin-pass-1")

    resp = await client.get(
        "/api/admin/mandanten/00000000-0000-0000-0000-000000000000",
        headers=auth_headers(token),
    )
    assert resp.status_code == 404
