import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_feed_returns_cards_with_expected_fields(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, name="Testkunde GmbH")
    await make_vorgang(mandant=mandant, kunde=kunde, titel="Testvorgang")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/feed", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    card = body["items"][0]
    assert card["kunde_name"] == "Testkunde GmbH"
    assert card["timer_laeuft"] is False
    assert card["tags"] == []


@pytest.mark.asyncio
async def test_feed_cursor_pagination_is_chronological_and_exhaustive(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    for i in range(5):
        await make_vorgang(mandant=mandant, kunde=kunde, titel=f"Vorgang {i}")
    token = await login(client, admin.email, "pw-123456")

    seen_ids = []
    cursor = None
    for _ in range(10):  # safety bound
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        resp = await client.get("/api/feed", headers=auth_headers(token), params=params)
        assert resp.status_code == 200
        body = resp.json()
        seen_ids += [item["id"] for item in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert len(seen_ids) == 5
    assert len(set(seen_ids)) == 5  # keine Duplikate über die Seiten hinweg


@pytest.mark.asyncio
async def test_feed_filters_by_status_and_tag(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    v1 = await make_vorgang(mandant=mandant, kunde=kunde, titel="Offen", status="neu")
    await make_vorgang(mandant=mandant, kunde=kunde, titel="Erledigt", status="abgeschlossen")
    token = await login(client, admin.email, "pw-123456")

    tag_resp = await client.post(
        "/api/tags", headers=auth_headers(token), json={"label": "dringend"}
    )
    tag_id = tag_resp.json()["id"]
    await client.post(
        f"/api/tags/{tag_id}/assignments",
        headers=auth_headers(token),
        json={"entity_type": "vorgang", "entity_id": str(v1.id)},
    )

    status_resp = await client.get(
        "/api/feed", headers=auth_headers(token), params={"status": "neu"}
    )
    assert [i["titel"] for i in status_resp.json()["items"]] == ["Offen"]

    tag_filter_resp = await client.get(
        "/api/feed", headers=auth_headers(token), params={"tag": "dringend"}
    )
    assert [i["titel"] for i in tag_filter_resp.json()["items"]] == ["Offen"]


@pytest.mark.asyncio
async def test_feed_shows_last_event_preview(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    await client.post(
        f"/api/vorgaenge/{vorgang.id}/events",
        headers=auth_headers(token),
        json={"event_type": "kommentar", "body": "Bin gleich vor Ort"},
    )

    resp = await client.get("/api/feed", headers=auth_headers(token))
    card = resp.json()["items"][0]
    assert card["letztes_event_vorschau"] == "Bin gleich vor Ort"


@pytest.mark.asyncio
async def test_feed_is_scoped_to_own_mandant(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    admin_a = await make_user(mandant=mandant_a, role="mandant_admin", password="pw-123456")
    kunde_a = await make_kunde(mandant=mandant_a)
    kunde_b = await make_kunde(mandant=mandant_b)
    await make_vorgang(mandant=mandant_a, kunde=kunde_a, titel="A")
    await make_vorgang(mandant=mandant_b, kunde=kunde_b, titel="B")
    token = await login(client, admin_a.email, "pw-123456")

    resp = await client.get("/api/feed", headers=auth_headers(token))
    assert [i["titel"] for i in resp.json()["items"]] == ["A"]
