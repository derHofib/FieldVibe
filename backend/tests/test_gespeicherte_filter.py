import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_gespeicherter_filter_crud(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    create = await client.post(
        "/api/gespeicherte-filter",
        headers=auth_headers(token),
        json={"entitaet": "vorgaenge", "name": "Meine offenen", "filter_json": {"status": "neu"}},
    )
    assert create.status_code == 201
    filter_id = create.json()["id"]
    assert create.json()["ist_standard"] is False

    listed = await client.get(
        "/api/gespeicherte-filter?entitaet=vorgaenge", headers=auth_headers(token)
    )
    assert [f["name"] for f in listed.json()] == ["Meine offenen"]

    update = await client.patch(
        f"/api/gespeicherte-filter/{filter_id}",
        headers=auth_headers(token),
        json={"filter_json": {"status": "in_arbeit"}},
    )
    assert update.status_code == 200
    assert update.json()["filter_json"] == {"status": "in_arbeit"}

    delete = await client.delete(
        f"/api/gespeicherte-filter/{filter_id}", headers=auth_headers(token)
    )
    assert delete.status_code == 204
    listed_after = await client.get(
        "/api/gespeicherte-filter?entitaet=vorgaenge", headers=auth_headers(token)
    )
    assert listed_after.json() == []


@pytest.mark.asyncio
async def test_nur_ein_standard_filter_je_nutzer_und_entitaet(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    erster = await client.post(
        "/api/gespeicherte-filter",
        headers=auth_headers(token),
        json={
            "entitaet": "vorgaenge",
            "name": "A",
            "filter_json": {"status": "neu"},
            "ist_standard": True,
        },
    )
    zweiter = await client.post(
        "/api/gespeicherte-filter",
        headers=auth_headers(token),
        json={
            "entitaet": "vorgaenge",
            "name": "B",
            "filter_json": {"status": "abgeschlossen"},
            "ist_standard": True,
        },
    )
    assert zweiter.json()["ist_standard"] is True

    listed = await client.get(
        "/api/gespeicherte-filter?entitaet=vorgaenge", headers=auth_headers(token)
    )
    standards = {f["name"]: f["ist_standard"] for f in listed.json()}
    assert standards == {"A": False, "B": True}
    assert erster.status_code == 201


@pytest.mark.asyncio
async def test_gespeicherter_filter_ist_personenbezogen(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456", email="admin@a.de")
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456", email="disp@a.de")
    admin_token = await login(client, admin.email, "pw-123456")
    disponent_token = await login(client, disponent.email, "pw-123456")

    create = await client.post(
        "/api/gespeicherte-filter",
        headers=auth_headers(admin_token),
        json={"entitaet": "vorgaenge", "name": "Nur meins", "filter_json": {}},
    )
    filter_id = create.json()["id"]

    listed_disponent = await client.get(
        "/api/gespeicherte-filter?entitaet=vorgaenge", headers=auth_headers(disponent_token)
    )
    assert listed_disponent.json() == []

    delete_fremd = await client.delete(
        f"/api/gespeicherte-filter/{filter_id}", headers=auth_headers(disponent_token)
    )
    assert delete_fremd.status_code == 404


@pytest.mark.asyncio
async def test_gespeicherter_filter_doppelter_name_konflikt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    await client.post(
        "/api/gespeicherte-filter",
        headers=auth_headers(token),
        json={"entitaet": "vorgaenge", "name": "Dringend", "filter_json": {}},
    )
    konflikt = await client.post(
        "/api/gespeicherte-filter",
        headers=auth_headers(token),
        json={"entitaet": "vorgaenge", "name": "Dringend", "filter_json": {}},
    )
    assert konflikt.status_code == 409
