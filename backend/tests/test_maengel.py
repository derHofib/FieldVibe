import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_techniker_can_report_mangel(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/maengel",
        headers=auth_headers(token),
        json={"vorgang_id": str(vorgang.id), "beschreibung": "Kabel beschädigt", "schweregrad": "hoch"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "offen"
    assert body["gemeldet_von"] == str(techniker.id)

    events_resp = await client.get(f"/api/vorgaenge/{vorgang.id}/events", headers=auth_headers(token))
    event_types = [e["event_type"] for e in events_resp.json()]
    assert "mangel" in event_types


@pytest.mark.asyncio
async def test_invalid_schweregrad_rejected(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/maengel",
        headers=auth_headers(token),
        json={"vorgang_id": str(vorgang.id), "beschreibung": "x", "schweregrad": "katastrophal"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_direct_status_transition_to_behoben_allowed(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, techniker.email, "pw-123456")

    created = await client.post(
        "/api/maengel",
        headers=auth_headers(token),
        json={"vorgang_id": str(vorgang.id), "beschreibung": "Sicherung locker"},
    )
    mangel_id = created.json()["id"]

    resp = await client.patch(
        f"/api/maengel/{mangel_id}", headers=auth_headers(token), json={"status": "behoben"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "behoben"
    assert resp.json()["behoben_am"] is not None


@pytest.mark.asyncio
async def test_direct_status_transition_to_in_bearbeitung_rejected(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, techniker.email, "pw-123456")

    created = await client.post(
        "/api/maengel",
        headers=auth_headers(token),
        json={"vorgang_id": str(vorgang.id), "beschreibung": "x"},
    )
    mangel_id = created.json()["id"]

    resp = await client.patch(
        f"/api/maengel/{mangel_id}", headers=auth_headers(token), json={"status": "in_bearbeitung"}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_maengel_protokoll_pdf(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, techniker.email, "pw-123456")

    await client.post(
        "/api/maengel",
        headers=auth_headers(token),
        json={"vorgang_id": str(vorgang.id), "beschreibung": "Kabelbruch"},
    )

    resp = await client.get(
        "/api/maengel/protokoll/pdf", headers=auth_headers(token), params={"vorgang_id": str(vorgang.id)}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_mandant_isolation_for_maengel(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    techniker1 = await make_user(mandant=mandant1, role="techniker", password="pw-123456")
    admin2 = await make_user(mandant=mandant2, role="mandant_admin", password="pw-123456")
    kunde1 = await make_kunde(mandant=mandant1)
    vorgang1 = await make_vorgang(mandant=mandant1, kunde=kunde1)
    token1 = await login(client, techniker1.email, "pw-123456")
    token2 = await login(client, admin2.email, "pw-123456")

    created = await client.post(
        "/api/maengel",
        headers=auth_headers(token1),
        json={"vorgang_id": str(vorgang1.id), "beschreibung": "x"},
    )
    assert created.status_code == 201
    mangel_id = created.json()["id"]

    list_resp = await client.get("/api/maengel", headers=auth_headers(token2))
    assert list_resp.json() == []

    get_resp = await client.get(f"/api/maengel/{mangel_id}", headers=auth_headers(token2))
    assert get_resp.status_code == 404
