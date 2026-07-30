import uuid

import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_techniker_can_create_vorgang(
    client, make_mandant, make_user, make_kunde, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/vorgaenge",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "titel": "Sicherung ausgelöst",
            "abrechnungsart": "aufwand",
            "leistungstyp": "stoerung",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["vorgangsnummer"] == "V-00001"
    assert body["status"] == "neu"

    # Anlegen erzeugt automatisch ein System-Event im Chat.
    events = await client.get(
        f"/api/vorgaenge/{body['id']}/events", headers=auth_headers(token)
    )
    assert events.status_code == 200
    assert len(events.json()) == 1
    assert events.json()[0]["is_system"] is True


@pytest.mark.asyncio
async def test_create_vorgang_mit_client_uuid_ist_idempotent(
    client, make_mandant, make_user, make_kunde, make_kunde_zuweisung
):
    """Simuliert einen Offline-Outbox-Sync-Retry: derselbe client_uuid darf
    nie einen zweiten Vorgang anlegen, egal wie oft der Request wiederholt
    wird (z.B. weil die App zwischen Senden und Antwort beendet wurde)."""
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")
    client_uuid = str(uuid.uuid4())

    payload = {
        "kunde_id": str(kunde.id),
        "titel": "Offline angelegt",
        "abrechnungsart": "aufwand",
        "leistungstyp": "stoerung",
        "client_uuid": client_uuid,
    }

    first = await client.post("/api/vorgaenge", headers=auth_headers(token), json=payload)
    assert first.status_code == 201
    vorgang_id = first.json()["id"]

    retry = await client.post("/api/vorgaenge", headers=auth_headers(token), json=payload)
    assert retry.status_code == 200
    assert retry.json()["id"] == vorgang_id

    list_resp = await client.get("/api/vorgaenge", headers=auth_headers(token))
    assert len([v for v in list_resp.json() if v["id"] == vorgang_id]) == 1


@pytest.mark.asyncio
async def test_abrechnungsart_und_leistungstyp_sind_unabhaengig(
    client, make_mandant, make_user, make_kunde
):
    """Jede Kombination aus abrechnungsart x leistungstyp muss zulässig sein."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/vorgaenge",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "titel": "DGUV-Prüfung im Gewährleistungsfall",
            "abrechnungsart": "gewaehrleistung",
            "leistungstyp": "pruefung",
        },
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_anlage_muss_zum_kunden_gehoeren(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde1 = await make_kunde(mandant=mandant, name="Kunde 1")
    kunde2 = await make_kunde(mandant=mandant, name="Kunde 2")
    anlage_von_kunde1 = await make_anlage(mandant=mandant, kunde=kunde1)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/vorgaenge",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde2.id),
            "anlage_id": str(anlage_von_kunde1.id),
            "titel": "Inkonsistent",
            "abrechnungsart": "aufwand",
            "leistungstyp": "stoerung",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_status_change_erzeugt_event_und_setzt_abgeschlossen_am(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}",
        headers=auth_headers(token),
        json={"status": "abgeschlossen"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "abgeschlossen"
    assert body["abgeschlossen_am"] is not None

    events = await client.get(
        f"/api/vorgaenge/{vorgang.id}/events", headers=auth_headers(token)
    )
    status_events = [e for e in events.json() if e["event_type"] == "status_change"]
    assert len(status_events) == 1
    assert status_events[0]["payload"] == {"von": "neu", "nach": "abgeschlossen"}


@pytest.mark.asyncio
async def test_feed_sortiert_nach_last_activity_at(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    older = await make_vorgang(mandant=mandant, kunde=kunde, titel="Älter")
    newer = await make_vorgang(mandant=mandant, kunde=kunde, titel="Neuer")
    token = await login(client, admin.email, "pw-123456")

    # Ein neues Event auf "older" muss last_activity_at anheben und es an
    # die Spitze des Feeds befördern (DB-Trigger, siehe Migration 0002).
    await client.post(
        f"/api/vorgaenge/{older.id}/events",
        headers=auth_headers(token),
        json={"event_type": "kommentar", "body": "Rückruf nötig"},
    )

    resp = await client.get("/api/vorgaenge", headers=auth_headers(token))
    ids_in_order = [v["id"] for v in resp.json()]
    assert ids_in_order.index(str(older.id)) < ids_in_order.index(str(newer.id))


@pytest.mark.asyncio
async def test_vorgang_filter_by_status_and_leistungstyp(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    await make_vorgang(mandant=mandant, kunde=kunde, leistungstyp="pruefung", status="geplant")
    await make_vorgang(mandant=mandant, kunde=kunde, leistungstyp="stoerung", status="neu")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get(
        "/api/vorgaenge",
        headers=auth_headers(token),
        params={"leistungstyp": "pruefung"},
    )
    assert resp.status_code == 200
    assert all(v["leistungstyp"] == "pruefung" for v in resp.json())


@pytest.mark.asyncio
async def test_vorgang_kann_an_anderen_kunden_gebunden_werden(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde1 = await make_kunde(mandant=mandant, name="Kunde 1")
    kunde2 = await make_kunde(mandant=mandant, name="Kunde 2")
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde1)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde2.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["kunde_id"] == str(kunde2.id)

    # Der Vorgang taucht danach nur noch bei Kunde 2 auf, nicht mehr bei Kunde 1.
    profil1 = await client.get(f"/api/kunden/{kunde1.id}/profil", headers=auth_headers(token))
    assert profil1.json()["vorgaenge"] == []
    profil2 = await client.get(f"/api/kunden/{kunde2.id}/profil", headers=auth_headers(token))
    assert [v["id"] for v in profil2.json()["vorgaenge"]] == [str(vorgang.id)]

    events_resp = await client.get(
        f"/api/vorgaenge/{vorgang.id}/events", headers=auth_headers(token)
    )
    kunde_events = [e for e in events_resp.json() if "Kunde geändert" in (e["body"] or "")]
    assert len(kunde_events) == 1


@pytest.mark.asyncio
async def test_vorgang_kann_an_anlage_fixiert_werden(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}",
        headers=auth_headers(token),
        json={"anlage_id": str(anlage.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["anlage_id"] == str(anlage.id)

    profil = await client.get(f"/api/anlagen/{anlage.id}/profil", headers=auth_headers(token))
    assert [v["id"] for v in profil.json()["vorgaenge"]] == [str(vorgang.id)]


@pytest.mark.asyncio
async def test_kundenwechsel_entfernt_nicht_mehr_passende_anlage(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde1 = await make_kunde(mandant=mandant, name="Kunde 1")
    kunde2 = await make_kunde(mandant=mandant, name="Kunde 2")
    anlage_von_kunde1 = await make_anlage(mandant=mandant, kunde=kunde1)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde1, anlage_id=anlage_von_kunde1.id)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde2.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["kunde_id"] == str(kunde2.id)
    assert resp.json()["anlage_id"] is None


@pytest.mark.asyncio
async def test_kunde_und_anlage_gemeinsam_wechseln(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde1 = await make_kunde(mandant=mandant, name="Kunde 1")
    kunde2 = await make_kunde(mandant=mandant, name="Kunde 2")
    anlage_von_kunde2 = await make_anlage(mandant=mandant, kunde=kunde2)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde1)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde2.id), "anlage_id": str(anlage_von_kunde2.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["kunde_id"] == str(kunde2.id)
    assert resp.json()["anlage_id"] == str(anlage_von_kunde2.id)


@pytest.mark.asyncio
async def test_neue_anlage_muss_zum_neuen_kunden_gehoeren(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde1 = await make_kunde(mandant=mandant, name="Kunde 1")
    kunde2 = await make_kunde(mandant=mandant, name="Kunde 2")
    anlage_von_kunde1 = await make_anlage(mandant=mandant, kunde=kunde1)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde1)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde2.id), "anlage_id": str(anlage_von_kunde1.id)},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_techniker_kann_vorgang_nicht_zu_nicht_zugewiesenem_kunden_binden(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde_eigen = await make_kunde(mandant=mandant, name="Eigener Kunde")
    kunde_fremd = await make_kunde(mandant=mandant, name="Fremder Kunde")
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde_eigen, techniker=techniker)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde_eigen)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde_fremd.id)},
    )
    assert resp.status_code == 403
