import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_disponent_can_create_and_list_kunden(client, make_mandant, make_user):
    mandant = await make_mandant()
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    token = await login(client, disponent.email, "pw-123456")

    resp = await client.post(
        "/api/kunden",
        headers=auth_headers(token),
        json={"name": "Müller Immobilien GmbH", "typ": "gewerbe"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["kundennummer"] == "K-00001"

    list_resp = await client.get("/api/kunden", headers=auth_headers(token))
    assert list_resp.status_code == 200
    assert any(k["name"] == "Müller Immobilien GmbH" for k in list_resp.json())


@pytest.mark.asyncio
async def test_kundennummer_auto_increments_per_mandant(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    first = await client.post(
        "/api/kunden", headers=auth_headers(token), json={"name": "Kunde A"}
    )
    second = await client.post(
        "/api/kunden", headers=auth_headers(token), json={"name": "Kunde B"}
    )
    assert first.json()["kundennummer"] == "K-00001"
    assert second.json()["kundennummer"] == "K-00002"


@pytest.mark.asyncio
async def test_techniker_can_read_but_not_create_kunden(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    list_resp = await client.get("/api/kunden", headers=auth_headers(token))
    assert list_resp.status_code == 200

    create_resp = await client.post(
        "/api/kunden", headers=auth_headers(token), json={"name": "Verboten GmbH"}
    )
    assert create_resp.status_code == 403


@pytest.mark.asyncio
async def test_duplicate_kundennummer_conflicts(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    payload = {"name": "Kunde A", "kundennummer": "MANUELL-1"}
    first = await client.post("/api/kunden", headers=auth_headers(token), json=payload)
    assert first.status_code == 201

    second = await client.post(
        "/api/kunden",
        headers=auth_headers(token),
        json={"name": "Kunde B", "kundennummer": "MANUELL-1"},
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_kunde_update(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/kunden/{kunde.id}", headers=auth_headers(token), json={"notiz": "Wichtiger Kunde"}
    )
    assert resp.status_code == 200
    assert resp.json()["notiz"] == "Wichtiger Kunde"


@pytest.mark.asyncio
async def test_unknown_kunde_returns_404(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get(
        "/api/kunden/00000000-0000-0000-0000-000000000000", headers=auth_headers(token)
    )
    assert resp.status_code == 404
