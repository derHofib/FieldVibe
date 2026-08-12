from datetime import datetime, timezone

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
async def test_feed_sortiert_nach_prioritaet(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    niedrig = await make_vorgang(mandant=mandant, kunde=kunde, titel="Niedrig", prioritaet=1)
    hoch = await make_vorgang(mandant=mandant, kunde=kunde, titel="Hoch", prioritaet=5)
    mittel = await make_vorgang(mandant=mandant, kunde=kunde, titel="Mittel", prioritaet=3)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get(
        "/api/feed", headers=auth_headers(token), params={"sort": "prioritaet"}
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert ids == [str(hoch.id), str(mittel.id), str(niedrig.id)]


@pytest.mark.asyncio
async def test_feed_cursor_pagination_nach_prioritaet_ist_exhaustiv(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    for i in range(5):
        await make_vorgang(mandant=mandant, kunde=kunde, titel=f"Vorgang {i}", prioritaet=(i % 5) + 1)
    token = await login(client, admin.email, "pw-123456")

    seen_ids = []
    cursor = None
    for _ in range(10):  # safety bound
        params = {"limit": 2, "sort": "prioritaet"}
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
    assert len(set(seen_ids)) == 5


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
async def test_feed_filtert_nach_mehreren_status(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    await make_vorgang(mandant=mandant, kunde=kunde, titel="Neu", status="neu")
    await make_vorgang(mandant=mandant, kunde=kunde, titel="Läuft", status="in_arbeit")
    await make_vorgang(mandant=mandant, kunde=kunde, titel="Erledigt", status="abgeschlossen")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get(
        "/api/feed", headers=auth_headers(token), params={"status": "neu,in_arbeit"}
    )
    assert {i["titel"] for i in resp.json()["items"]} == {"Neu", "Läuft"}


@pytest.mark.asyncio
async def test_feed_zeigt_anlage_standort_und_ersteller(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    standort = await client.post(
        "/api/standorte",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "bezeichnung": "Filiale Nord"},
    )
    standort_id = standort.json()["id"]
    anlage = await client.post(
        "/api/anlagen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "standort_id": standort_id, "bezeichnung": "Hauptverteilung"},
    )
    anlage_id = anlage.json()["id"]

    create = await client.post(
        "/api/vorgaenge",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "anlage_id": anlage_id,
            "standort_id": standort_id,
            "titel": "Wartung",
            "abrechnungsart": "aufwand",
            "leistungstyp": "wartung",
            "faelligkeit_am": "2026-09-01T10:00:00Z",
        },
    )
    assert create.status_code == 201
    assert create.json()["erstellt_von"] == str(admin.id)

    resp = await client.get("/api/feed", headers=auth_headers(token))
    card = resp.json()["items"][0]
    assert card["anlage_bezeichnung"] == "Hauptverteilung"
    assert card["standort_bezeichnung"] == "Filiale Nord"
    assert card["ersteller_name"] == admin.name
    assert card["faelligkeit_am"].startswith("2026-09-01")


@pytest.mark.asyncio
async def test_feed_zeigt_koordinaten_vom_standort_wenn_vorhanden(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    standort = await client.post(
        "/api/standorte",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "bezeichnung": "Filiale Nord",
            "geo_lat": 52.52,
            "geo_lng": 13.405,
        },
    )
    standort_id = standort.json()["id"]
    anlage = await client.post(
        "/api/anlagen",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "standort_id": standort_id,
            "bezeichnung": "Hauptverteilung",
            "geo_lat": 1.0,
            "geo_lng": 2.0,
        },
    )
    anlage_id = anlage.json()["id"]

    await client.post(
        "/api/vorgaenge",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "anlage_id": anlage_id,
            "standort_id": standort_id,
            "titel": "Wartung",
            "abrechnungsart": "aufwand",
            "leistungstyp": "wartung",
        },
    )

    resp = await client.get("/api/feed", headers=auth_headers(token))
    card = resp.json()["items"][0]
    # Standort hat Vorrang vor der Anlage (siehe app/api/routes/feed.py).
    assert card["geo_lat"] == pytest.approx(52.52)
    assert card["geo_lng"] == pytest.approx(13.405)


@pytest.mark.asyncio
async def test_feed_zeigt_koordinaten_von_anlage_ohne_standort(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    anlage = await client.post(
        "/api/anlagen",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "bezeichnung": "Hauptverteilung",
            "geo_lat": 48.14,
            "geo_lng": 11.58,
        },
    )
    anlage_id = anlage.json()["id"]

    await client.post(
        "/api/vorgaenge",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "anlage_id": anlage_id,
            "titel": "Wartung",
            "abrechnungsart": "aufwand",
            "leistungstyp": "wartung",
        },
    )

    resp = await client.get("/api/feed", headers=auth_headers(token))
    card = resp.json()["items"][0]
    assert card["geo_lat"] == pytest.approx(48.14)
    assert card["geo_lng"] == pytest.approx(11.58)


@pytest.mark.asyncio
async def test_feed_ohne_koordinaten_wenn_vorgang_eigene_adresse_hat(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    anlage = await client.post(
        "/api/anlagen",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "bezeichnung": "Hauptverteilung",
            "geo_lat": 48.14,
            "geo_lng": 11.58,
        },
    )
    anlage_id = anlage.json()["id"]

    # Manueller Adress-Override am Vorgang -- die Anlage-Koordinaten
    # gehoeren dann zu einem ganz anderen Ort und duerfen nicht mit
    # angezeigt werden (siehe gleiche Regel in VorgangDetailPage.tsx).
    await client.post(
        "/api/vorgaenge",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "anlage_id": anlage_id,
            "titel": "Wartung",
            "abrechnungsart": "aufwand",
            "leistungstyp": "wartung",
            "adresse": {"strasse": "Andere Str. 5", "ort": "Woanders"},
        },
    )

    resp = await client.get("/api/feed", headers=auth_headers(token))
    card = resp.json()["items"][0]
    assert card["geo_lat"] is None
    assert card["geo_lng"] is None


@pytest.mark.asyncio
async def test_feed_filtert_nach_faelligkeit(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    await make_vorgang(
        mandant=mandant,
        kunde=kunde,
        titel="Bald fällig",
        faelligkeit_am=datetime(2026, 1, 5, tzinfo=timezone.utc),
    )
    await make_vorgang(
        mandant=mandant,
        kunde=kunde,
        titel="Spät fällig",
        faelligkeit_am=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    await make_vorgang(mandant=mandant, kunde=kunde, titel="Ohne Frist")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get(
        "/api/feed",
        headers=auth_headers(token),
        params={"faellig_von": "2026-01-01", "faellig_bis": "2026-02-01"},
    )
    assert [i["titel"] for i in resp.json()["items"]] == ["Bald fällig"]


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
