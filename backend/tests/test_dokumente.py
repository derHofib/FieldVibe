import uuid

import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_upload_dokument_creates_event_with_url(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        f"/api/vorgaenge/{vorgang.id}/events/dokument",
        headers=auth_headers(token),
        files={"file": ("Datenblatt.pdf", b"%PDF-1.4 fake content", "application/pdf")},
        data={"kundensichtbar": "true", "body": "Datenblatt vom Hersteller"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["event_type"] == "dokument"
    assert body["kundensichtbar"] is True
    assert body["dokument_url"] is not None
    assert body["dokument_dateiname"] == "Datenblatt.pdf"
    assert body["payload"]["size"] > 0


@pytest.mark.asyncio
async def test_upload_dokument_akzeptiert_beliebigen_dateityp(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        f"/api/vorgaenge/{vorgang.id}/events/dokument",
        headers=auth_headers(token),
        files={
            "file": (
                "Aufmass.xlsx",
                b"fake xlsx content",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert resp.status_code == 201
    assert resp.json()["dokument_dateiname"] == "Aufmass.xlsx"


@pytest.mark.asyncio
async def test_upload_dokument_client_uuid_replay_is_idempotent(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    client_uuid = str(uuid.uuid4())
    files = {"file": ("Protokoll.pdf", b"%PDF-1.4", "application/pdf")}

    first = await client.post(
        f"/api/vorgaenge/{vorgang.id}/events/dokument",
        headers=auth_headers(token),
        files=files,
        data={"client_uuid": client_uuid},
    )
    assert first.status_code == 201
    first_id = first.json()["id"]

    replay = await client.post(
        f"/api/vorgaenge/{vorgang.id}/events/dokument",
        headers=auth_headers(token),
        files=files,
        data={"client_uuid": client_uuid},
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == first_id


@pytest.mark.asyncio
async def test_upload_dokument_fuer_abgeschlossenen_vorgang_409(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, status="abgeschlossen")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        f"/api/vorgaenge/{vorgang.id}/events/dokument",
        headers=auth_headers(token),
        files={"file": ("Protokoll.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_uploaded_dokument_appears_in_event_list(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    await client.post(
        f"/api/vorgaenge/{vorgang.id}/events/dokument",
        headers=auth_headers(token),
        files={"file": ("Protokoll.pdf", b"%PDF-1.4", "application/pdf")},
    )

    events_resp = await client.get(f"/api/vorgaenge/{vorgang.id}/events", headers=auth_headers(token))
    dokument_events = [e for e in events_resp.json() if e["event_type"] == "dokument"]
    assert len(dokument_events) == 1
    assert dokument_events[0]["dokument_url"] is not None


@pytest.mark.asyncio
async def test_upload_dokument_for_unknown_vorgang_404(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/vorgaenge/00000000-0000-0000-0000-000000000000/events/dokument",
        headers=auth_headers(token),
        files={"file": ("Protokoll.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert resp.status_code == 404
