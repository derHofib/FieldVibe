import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_mandant_admin_can_create_user_in_own_mandant(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/users",
        headers=auth_headers(token),
        json={
            "mandant_id": str(mandant.id),
            "email": "neu@example.de",
            "password": "supersecret1",
            "role": "techniker",
            "name": "Neuer Techniker",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "techniker"


@pytest.mark.asyncio
async def test_mandant_admin_cannot_create_user_in_other_mandant(
    client, make_mandant, make_user
):
    own_mandant = await make_mandant(name="Eigen")
    other_mandant = await make_mandant(name="Fremd")
    admin = await make_user(
        mandant=own_mandant, role="mandant_admin", password="pw-123456"
    )
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/users",
        headers=auth_headers(token),
        json={
            "mandant_id": str(other_mandant.id),
            "email": "eindringling@example.de",
            "password": "supersecret1",
            "role": "techniker",
            "name": "Eindringling",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_mandant_admin_cannot_create_super_admin(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/users",
        headers=auth_headers(token),
        json={
            "mandant_id": None,
            "email": "wannabe-admin@example.de",
            "password": "supersecret1",
            "role": "super_admin",
            "name": "Wannabe",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_techniker_cannot_manage_users(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.get("/api/users", headers=auth_headers(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_super_admin_can_create_users_across_mandanten(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")
    token = await login(client, super_admin.email, "pw-123456")

    resp = await client.post(
        "/api/users",
        headers=auth_headers(token),
        json={
            "mandant_id": str(mandant.id),
            "email": "von-super-admin@example.de",
            "password": "supersecret1",
            "role": "disponent",
            "name": "Von Super Admin",
        },
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_deactivate_user(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    target = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/users/{target.id}",
        headers=auth_headers(token),
        json={"aktiv": False},
    )
    assert resp.status_code == 200
    assert resp.json()["aktiv"] is False

    login_resp = await client.post(
        "/api/auth/login", json={"email": target.email, "password": "pw-123456"}
    )
    assert login_resp.status_code == 403
