import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_search_finds_kunde_by_partial_name(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    await make_kunde(mandant=mandant, name="Café Sonnenschein")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/search", headers=auth_headers(token), params={"q": "Sonnensch"})
    assert resp.status_code == 200
    kategorien = {t["kategorie"] for t in resp.json()["treffer"]}
    assert "kunde" in kategorien


@pytest.mark.asyncio
async def test_search_finds_vorgang_by_vorgangsnummer(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(
        mandant=mandant, kunde=kunde, vorgangsnummer="V-99999", titel="Ganz spezieller Titel"
    )
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/search", headers=auth_headers(token), params={"q": "V-99999"})
    treffer = resp.json()["treffer"]
    assert any(t["id"] == str(vorgang.id) for t in treffer)


@pytest.mark.asyncio
async def test_search_finds_vorgang_by_kommentar_volltext(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, titel="Allgemeiner Titel")
    token = await login(client, admin.email, "pw-123456")

    await client.post(
        f"/api/vorgaenge/{vorgang.id}/events",
        headers=auth_headers(token),
        json={"event_type": "kommentar", "body": "Kaputte Zählerschranktür ausgetauscht"},
    )

    resp = await client.get(
        "/api/search", headers=auth_headers(token), params={"q": "Zählerschranktür"}
    )
    treffer = resp.json()["treffer"]
    assert any(t["id"] == str(vorgang.id) for t in treffer)


@pytest.mark.asyncio
async def test_search_with_hash_only_searches_tags(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    await client.post("/api/tags", headers=auth_headers(token), json={"label": "wallbox"})

    resp = await client.get("/api/search", headers=auth_headers(token), params={"q": "#wall"})
    treffer = resp.json()["treffer"]
    assert all(t["kategorie"] == "tag" for t in treffer)
    assert any(t["titel"] == "#wallbox" for t in treffer)


@pytest.mark.asyncio
async def test_search_is_scoped_to_own_mandant(client, make_mandant, make_user, make_kunde):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    admin_a = await make_user(mandant=mandant_a, role="mandant_admin", password="pw-123456")
    await make_kunde(mandant=mandant_b, name="Nur in Mandant B GmbH")
    token = await login(client, admin_a.email, "pw-123456")

    resp = await client.get(
        "/api/search", headers=auth_headers(token), params={"q": "Mandant B"}
    )
    assert resp.json()["treffer"] == []
