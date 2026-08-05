import uuid

import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_create_comment_event(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        f"/api/vorgaenge/{vorgang.id}/events",
        headers=auth_headers(token),
        json={"event_type": "kommentar", "body": "Vor Ort eingetroffen"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["kundensichtbar"] is False
    assert body["is_system"] is False


@pytest.mark.asyncio
async def test_client_uuid_replay_is_idempotent(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")

    client_uuid = str(uuid.uuid4())
    payload = {"event_type": "kommentar", "body": "Offline erfasst", "client_uuid": client_uuid}

    first = await client.post(
        f"/api/vorgaenge/{vorgang.id}/events", headers=auth_headers(token), json=payload
    )
    assert first.status_code == 201
    first_id = first.json()["id"]

    replay = await client.post(
        f"/api/vorgaenge/{vorgang.id}/events", headers=auth_headers(token), json=payload
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == first_id

    events = await client.get(
        f"/api/vorgaenge/{vorgang.id}/events", headers=auth_headers(token)
    )
    matching = [e for e in events.json() if e["client_uuid"] == client_uuid]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_events_for_unknown_vorgang_404(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get(
        "/api/vorgaenge/00000000-0000-0000-0000-000000000000/events",
        headers=auth_headers(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_kundensichtbar_flag_is_respected(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        f"/api/vorgaenge/{vorgang.id}/events",
        headers=auth_headers(token),
        json={"event_type": "kommentar", "body": "Für Kunde sichtbar", "kundensichtbar": True},
    )
    assert resp.status_code == 201
    assert resp.json()["kundensichtbar"] is True
