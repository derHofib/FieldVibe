import pytest

from app.api.paginierung import MAX_LIMIT, STANDARD_LIMIT
from tests.conftest import auth_headers, login


async def _admin_token(client, make_mandant, make_user, mandant=None):
    mandant = mandant or await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    return await login(client, admin.email, "pw-123456")


async def _kunden_anlegen(client, token, namen):
    for name in namen:
        resp = await client.post("/api/kunden", headers=auth_headers(token), json={"name": name})
        assert resp.status_code == 201


@pytest.mark.asyncio
async def test_ohne_parameter_bleibt_verhalten_gleich_und_header_ist_gesetzt(client, make_mandant, make_user):
    token = await _admin_token(client, make_mandant, make_user)
    await _kunden_anlegen(client, token, ["A", "B", "C"])

    resp = await client.get("/api/kunden", headers=auth_headers(token))
    assert resp.status_code == 200
    assert [k["name"] for k in resp.json()] == ["A", "B", "C"]
    assert resp.headers["X-Total-Count"] == "3"
    # Antwortstruktur bleibt eine nackte Liste
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_limit_und_offset_blaettern_stabil_ohne_luecken_und_dubletten(client, make_mandant, make_user):
    token = await _admin_token(client, make_mandant, make_user)
    # Gleiche Namen: ohne id-Tiebreaker wuerde die Seitengrenze wackeln.
    await _kunden_anlegen(client, token, ["Gleich"] * 5 + ["Zeta"])

    gesehen = []
    for offset in (0, 2, 4):
        resp = await client.get(
            "/api/kunden", headers=auth_headers(token), params={"limit": 2, "offset": offset}
        )
        assert resp.status_code == 200
        assert resp.headers["X-Total-Count"] == "6"
        gesehen.extend(k["id"] for k in resp.json())
    assert len(gesehen) == 6
    assert len(set(gesehen)) == 6

    ueber_ende = await client.get(
        "/api/kunden", headers=auth_headers(token), params={"limit": 2, "offset": 10}
    )
    assert ueber_ende.json() == []
    assert ueber_ende.headers["X-Total-Count"] == "6"


@pytest.mark.asyncio
async def test_grenzen_werden_validiert(client, make_mandant, make_user):
    token = await _admin_token(client, make_mandant, make_user)
    for params in ({"limit": 0}, {"limit": MAX_LIMIT + 1}, {"offset": -1}):
        resp = await client.get("/api/kunden", headers=auth_headers(token), params=params)
        assert resp.status_code == 422, params
    ok = await client.get("/api/kunden", headers=auth_headers(token), params={"limit": MAX_LIMIT})
    assert ok.status_code == 200
    assert STANDARD_LIMIT <= MAX_LIMIT


@pytest.mark.asyncio
async def test_gesamtzahl_zaehlt_nur_den_eigenen_mandanten(client, make_mandant, make_user):
    token_a = await _admin_token(client, make_mandant, make_user)
    token_b = await _admin_token(client, make_mandant, make_user)
    await _kunden_anlegen(client, token_a, ["A1", "A2", "A3"])
    await _kunden_anlegen(client, token_b, ["B1"])

    resp = await client.get("/api/kunden", headers=auth_headers(token_b))
    assert [k["name"] for k in resp.json()] == ["B1"]
    assert resp.headers["X-Total-Count"] == "1"


@pytest.mark.asyncio
async def test_rechte_bleiben_unveraendert(client, make_mandant, make_user):
    mandant = await make_mandant()
    kunde_token = await _admin_token(client, make_mandant, make_user, mandant)
    await _kunden_anlegen(client, kunde_token, ["A"])

    # Ohne Anmeldung weiterhin 401, auch mit Paginierungsparametern.
    resp = await client.get("/api/kunden", params={"limit": 1})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_weitere_listen_liefern_header_und_respektieren_limit(client, make_mandant, make_user):
    token = await _admin_token(client, make_mandant, make_user)
    for name in ("P1", "P2", "P3"):
        resp = await client.post("/api/projekte", headers=auth_headers(token), json={"name": name})
        assert resp.status_code == 201
    for name in ("L1", "L2"):
        resp = await client.post("/api/lieferanten", headers=auth_headers(token), json={"name": name})
        assert resp.status_code == 201

    projekte = await client.get("/api/projekte", headers=auth_headers(token), params={"limit": 2})
    assert [p["name"] for p in projekte.json()] == ["P1", "P2"]
    assert projekte.headers["X-Total-Count"] == "3"

    lieferanten = await client.get(
        "/api/lieferanten", headers=auth_headers(token), params={"limit": 1, "offset": 1}
    )
    assert [x["name"] for x in lieferanten.json()] == ["L2"]
    assert lieferanten.headers["X-Total-Count"] == "2"

    for pfad in (
        "/api/standorte",
        "/api/anlagen",
        "/api/angebote",
        "/api/eingangsrechnungen",
        "/api/material",
        "/api/termine",
        "/api/notifications",
        "/api/bestellungen",
        "/api/zeiterfassung",
        "/api/maengel",
        "/api/auftraege",
        "/api/vorgaenge",
    ):
        resp = await client.get(pfad, headers=auth_headers(token), params={"limit": 5, "offset": 0})
        assert resp.status_code == 200, pfad
        # /api/anlagen: ein Projekt legt eine interne Baustellen-Anlage an.
        assert resp.headers["X-Total-Count"] == str(len(resp.json())), pfad
