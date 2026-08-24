import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_get_ohne_anpassung_ist_leer(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.get("/api/nav-kategorien", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["kategorien"] == []
    assert body["zuordnungen"] == {}


@pytest.mark.asyncio
async def test_techniker_darf_nicht_speichern(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.put(
        "/api/nav-kategorien",
        headers=auth_headers(token),
        json={"kategorien": [{"name": "Test", "reihenfolge": 0}], "zuordnungen": {}},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_kann_kategorien_setzen_und_wieder_lesen(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    put_resp = await client.put(
        "/api/nav-kategorien",
        headers=auth_headers(token),
        json={
            "kategorien": [
                {"name": "Tagesgeschäft", "reihenfolge": 0},
                {"name": "Büro", "reihenfolge": 1},
            ],
            "zuordnungen": {"material": "Tagesgeschäft", "partner": "Büro"},
        },
    )
    assert put_resp.status_code == 200
    body = put_resp.json()
    assert [k["name"] for k in body["kategorien"]] == ["Tagesgeschäft", "Büro"]
    assert body["zuordnungen"] == {"material": "Tagesgeschäft", "partner": "Büro"}

    get_resp = await client.get("/api/nav-kategorien", headers=auth_headers(token))
    assert get_resp.status_code == 200
    assert get_resp.json() == body


@pytest.mark.asyncio
async def test_doppelte_namen_werden_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.put(
        "/api/nav-kategorien",
        headers=auth_headers(token),
        json={
            "kategorien": [{"name": "Büro", "reihenfolge": 0}, {"name": "Büro", "reihenfolge": 1}],
            "zuordnungen": {},
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_zuordnung_auf_unbekannte_kategorie_wird_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.put(
        "/api/nav-kategorien",
        headers=auth_headers(token),
        json={
            "kategorien": [{"name": "Büro", "reihenfolge": 0}],
            "zuordnungen": {"material": "Werkstatt"},
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_umbenennen_und_loeschen_ueber_erneutes_put(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    await client.put(
        "/api/nav-kategorien",
        headers=auth_headers(token),
        json={
            "kategorien": [{"name": "Alt", "reihenfolge": 0}, {"name": "Wird gelöscht", "reihenfolge": 1}],
            "zuordnungen": {"material": "Alt"},
        },
    )

    # "Wird gelöscht" faellt raus, "Alt" wird umbenannt -- beides in einem
    # einzigen vollstaendigen Ersatz-PUT, wie es die Einstellungsseite tut.
    resp = await client.put(
        "/api/nav-kategorien",
        headers=auth_headers(token),
        json={
            "kategorien": [{"name": "Neu", "reihenfolge": 0}],
            "zuordnungen": {"material": "Neu"},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [k["name"] for k in body["kategorien"]] == ["Neu"]
    assert body["zuordnungen"] == {"material": "Neu"}


@pytest.mark.asyncio
async def test_mandanten_isolation(client, make_mandant, make_user):
    mandant_a = await make_mandant()
    admin_a = await make_user(mandant=mandant_a, role="mandant_admin", password="pw-123456")
    token_a = await login(client, admin_a.email, "pw-123456")
    await client.put(
        "/api/nav-kategorien",
        headers=auth_headers(token_a),
        json={"kategorien": [{"name": "Nur A", "reihenfolge": 0}], "zuordnungen": {}},
    )

    mandant_b = await make_mandant()
    admin_b = await make_user(mandant=mandant_b, role="mandant_admin", password="pw-123456")
    token_b = await login(client, admin_b.email, "pw-123456")

    resp = await client.get("/api/nav-kategorien", headers=auth_headers(token_b))
    assert resp.status_code == 200
    assert resp.json()["kategorien"] == []
