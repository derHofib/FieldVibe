from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import auth_headers, login


def _iso(dt: datetime) -> str:
    return dt.isoformat()


@pytest.mark.asyncio
async def test_disponent_can_create_termin(
    client, make_mandant, make_user, make_kunde, make_anlage, make_vorgang
):
    mandant = await make_mandant()
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, anlage_id=anlage.id)
    token = await login(client, disponent.email, "pw-123456")

    start = datetime.now(timezone.utc) + timedelta(days=1)
    resp = await client.post(
        "/api/termine",
        headers=auth_headers(token),
        json={
            "vorgang_id": str(vorgang.id),
            "techniker_id": str(techniker.id),
            "titel": "E-Check Hauptverteilung",
            "start_at": _iso(start),
            "ende_at": _iso(start + timedelta(hours=1)),
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["warnungen"] == []
    assert body["termin"]["techniker_id"] == str(techniker.id)
    assert body["termin"]["status"] == "geplant"

    tech_token = await login(client, techniker.email, "pw-123456")
    list_resp = await client.get(
        "/api/termine", headers=auth_headers(tech_token), params={"techniker_id": str(techniker.id)}
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


@pytest.mark.asyncio
async def test_techniker_cannot_create_termin(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, techniker.email, "pw-123456")

    start = datetime.now(timezone.utc) + timedelta(days=1)
    resp = await client.post(
        "/api/termine",
        headers=auth_headers(token),
        json={
            "vorgang_id": str(vorgang.id),
            "techniker_id": str(techniker.id),
            "titel": "Termin",
            "start_at": _iso(start),
            "ende_at": _iso(start + timedelta(hours=1)),
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_ende_before_start_rejected(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, disponent.email, "pw-123456")

    start = datetime.now(timezone.utc) + timedelta(days=1)
    resp = await client.post(
        "/api/termine",
        headers=auth_headers(token),
        json={
            "vorgang_id": str(vorgang.id),
            "techniker_id": str(techniker.id),
            "titel": "Termin",
            "start_at": _iso(start),
            "ende_at": _iso(start - timedelta(hours=1)),
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_overlapping_termin_warns_but_does_not_block(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang1 = await make_vorgang(mandant=mandant, kunde=kunde, titel="V1")
    vorgang2 = await make_vorgang(mandant=mandant, kunde=kunde, titel="V2")
    token = await login(client, disponent.email, "pw-123456")

    start = datetime.now(timezone.utc) + timedelta(days=1)
    first = await client.post(
        "/api/termine",
        headers=auth_headers(token),
        json={
            "vorgang_id": str(vorgang1.id),
            "techniker_id": str(techniker.id),
            "titel": "Erster Termin",
            "start_at": _iso(start),
            "ende_at": _iso(start + timedelta(hours=2)),
        },
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/termine",
        headers=auth_headers(token),
        json={
            "vorgang_id": str(vorgang2.id),
            "techniker_id": str(techniker.id),
            "titel": "Zweiter Termin",
            "start_at": _iso(start + timedelta(hours=1)),
            "ende_at": _iso(start + timedelta(hours=3)),
        },
    )
    assert second.status_code == 201
    warnungen = second.json()["warnungen"]
    assert len(warnungen) == 1
    assert warnungen[0]["typ"] == "ueberschneidung"
    assert warnungen[0]["anderer_termin_id"] == first.json()["termin"]["id"]


@pytest.mark.asyncio
async def test_tight_travel_time_between_distant_anlagen_warns(
    client, make_mandant, make_user, make_kunde, make_anlage, make_vorgang
):
    mandant = await make_mandant()
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    # Berlin und Muenchen -- ca. 500 km Luftlinie, in 15 Minuten unmoeglich.
    berlin = await make_anlage(mandant=mandant, kunde=kunde, geo_lat=52.52, geo_lng=13.40)
    muenchen = await make_anlage(mandant=mandant, kunde=kunde, geo_lat=48.14, geo_lng=11.58)
    vorgang1 = await make_vorgang(mandant=mandant, kunde=kunde, titel="V1", anlage_id=berlin.id)
    vorgang2 = await make_vorgang(mandant=mandant, kunde=kunde, titel="V2", anlage_id=muenchen.id)
    token = await login(client, disponent.email, "pw-123456")

    start = datetime.now(timezone.utc) + timedelta(days=1)
    first = await client.post(
        "/api/termine",
        headers=auth_headers(token),
        json={
            "vorgang_id": str(vorgang1.id),
            "techniker_id": str(techniker.id),
            "titel": "Berlin-Termin",
            "start_at": _iso(start),
            "ende_at": _iso(start + timedelta(hours=1)),
        },
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/termine",
        headers=auth_headers(token),
        json={
            "vorgang_id": str(vorgang2.id),
            "techniker_id": str(techniker.id),
            "titel": "Muenchen-Termin",
            "start_at": _iso(start + timedelta(hours=1, minutes=15)),
            "ende_at": _iso(start + timedelta(hours=2, minutes=15)),
        },
    )
    assert second.status_code == 201
    warnungen = second.json()["warnungen"]
    assert any(w["typ"] == "fahrzeit" for w in warnungen)


@pytest.mark.asyncio
async def test_comfortable_gap_same_location_no_warning(
    client, make_mandant, make_user, make_kunde, make_anlage, make_vorgang
):
    mandant = await make_mandant()
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde, geo_lat=52.52, geo_lng=13.40)
    vorgang1 = await make_vorgang(mandant=mandant, kunde=kunde, titel="V1", anlage_id=anlage.id)
    vorgang2 = await make_vorgang(mandant=mandant, kunde=kunde, titel="V2", anlage_id=anlage.id)
    token = await login(client, disponent.email, "pw-123456")

    start = datetime.now(timezone.utc) + timedelta(days=1)
    first = await client.post(
        "/api/termine",
        headers=auth_headers(token),
        json={
            "vorgang_id": str(vorgang1.id),
            "techniker_id": str(techniker.id),
            "titel": "Erster Termin",
            "start_at": _iso(start),
            "ende_at": _iso(start + timedelta(hours=1)),
        },
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/termine",
        headers=auth_headers(token),
        json={
            "vorgang_id": str(vorgang2.id),
            "techniker_id": str(techniker.id),
            "titel": "Zweiter Termin",
            "start_at": _iso(start + timedelta(hours=2)),
            "ende_at": _iso(start + timedelta(hours=3)),
        },
    )
    assert second.status_code == 201
    assert second.json()["warnungen"] == []


@pytest.mark.asyncio
async def test_update_termin_status_to_abgesagt(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, disponent.email, "pw-123456")

    start = datetime.now(timezone.utc) + timedelta(days=1)
    created = await client.post(
        "/api/termine",
        headers=auth_headers(token),
        json={
            "vorgang_id": str(vorgang.id),
            "techniker_id": str(techniker.id),
            "titel": "Termin",
            "start_at": _iso(start),
            "ende_at": _iso(start + timedelta(hours=1)),
        },
    )
    termin_id = created.json()["termin"]["id"]

    resp = await client.patch(
        f"/api/termine/{termin_id}", headers=auth_headers(token), json={"status": "abgesagt"}
    )
    assert resp.status_code == 200
    assert resp.json()["termin"]["status"] == "abgesagt"


@pytest.mark.asyncio
async def test_mandant_isolation_for_termine(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    disponent1 = await make_user(mandant=mandant1, role="disponent", password="pw-123456")
    techniker1 = await make_user(mandant=mandant1, role="techniker", password="pw-123456")
    disponent2 = await make_user(mandant=mandant2, role="disponent", password="pw-123456")
    kunde1 = await make_kunde(mandant=mandant1)
    vorgang1 = await make_vorgang(mandant=mandant1, kunde=kunde1)
    token1 = await login(client, disponent1.email, "pw-123456")
    token2 = await login(client, disponent2.email, "pw-123456")

    start = datetime.now(timezone.utc) + timedelta(days=1)
    created = await client.post(
        "/api/termine",
        headers=auth_headers(token1),
        json={
            "vorgang_id": str(vorgang1.id),
            "techniker_id": str(techniker1.id),
            "titel": "Termin",
            "start_at": _iso(start),
            "ende_at": _iso(start + timedelta(hours=1)),
        },
    )
    assert created.status_code == 201
    termin_id = created.json()["termin"]["id"]

    list_resp = await client.get("/api/termine", headers=auth_headers(token2))
    assert list_resp.json() == []

    get_resp = await client.get(f"/api/termine/{termin_id}", headers=auth_headers(token2))
    assert get_resp.status_code == 404
