import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_impersonate_mandant_logs_audit_and_scopes_token(
    client, make_mandant, make_user
):
    mandant = await make_mandant(name="Zielmandant")
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")
    token = await login(client, super_admin.email, "pw-123456")

    resp = await client.post(
        f"/api/admin/mandanten/{mandant.id}/impersonate",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    imp_token = resp.json()["access_token"]
    assert resp.json()["mandant_id"] == str(mandant.id)

    me_resp = await client.get("/api/auth/me", headers=auth_headers(imp_token))
    assert me_resp.status_code == 200
    body = me_resp.json()
    assert body["role"] == "mandant_admin"
    assert body["mandant_id"] == str(mandant.id)
    assert body["mandant_name"] == "Zielmandant"
    assert body["impersonated_by"] == str(super_admin.id)

    audit_resp = await client.get(
        "/api/admin/audit-log", headers=auth_headers(token)
    )
    assert audit_resp.status_code == 200
    entries = audit_resp.json()
    assert any(
        e["aktion"] == "login_als_mandant" and e["mandant_id"] == str(mandant.id)
        for e in entries
    )


@pytest.mark.asyncio
async def test_impersonation_scoped_session_respects_rls(
    client, make_mandant, make_user
):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")
    await make_user(mandant=mandant_a, role="techniker", password="pw-123456")
    await make_user(mandant=mandant_b, role="techniker", password="pw-123456")

    token = await login(client, super_admin.email, "pw-123456")
    imp_resp = await client.post(
        f"/api/admin/mandanten/{mandant_a.id}/impersonate",
        headers=auth_headers(token),
    )
    imp_token = imp_resp.json()["access_token"]

    users_resp = await client.get("/api/users", headers=auth_headers(imp_token))
    assert users_resp.status_code == 200
    seen_mandanten = {u["mandant_id"] for u in users_resp.json()}
    assert seen_mandanten == {str(mandant_a.id)}


@pytest.mark.asyncio
async def test_impersonate_unknown_mandant_returns_404(client, make_user):
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")
    token = await login(client, super_admin.email, "pw-123456")

    resp = await client.post(
        "/api/admin/mandanten/00000000-0000-0000-0000-000000000000/impersonate",
        headers=auth_headers(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_audit_log_requires_super_admin(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/admin/audit-log", headers=auth_headers(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_audit_log_filters_by_mandant_und_aktion(client, make_mandant, make_user):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")
    token = await login(client, super_admin.email, "pw-123456")

    await client.post(f"/api/admin/mandanten/{mandant_a.id}/impersonate", headers=auth_headers(token))
    await client.post(f"/api/admin/mandanten/{mandant_b.id}/impersonate", headers=auth_headers(token))

    resp = await client.get(
        "/api/admin/audit-log",
        params={"mandant_id": str(mandant_a.id)},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    entries = resp.json()
    assert entries
    assert all(e["mandant_id"] == str(mandant_a.id) for e in entries)

    resp = await client.get(
        "/api/admin/audit-log",
        params={"aktion": "login_als_mandant"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert all(e["aktion"] == "login_als_mandant" for e in resp.json())

    resp = await client.get(
        "/api/admin/audit-log",
        params={"aktion": "nichts_passt_hier"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_non_super_admin_cannot_impersonate(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        f"/api/admin/mandanten/{mandant.id}/impersonate",
        headers=auth_headers(token),
    )
    assert resp.status_code == 403
