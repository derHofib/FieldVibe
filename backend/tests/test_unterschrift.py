import io

import pytest
from PIL import Image

from tests.conftest import auth_headers, login


def _make_test_image_bytes(size=(300, 150)) -> bytes:
    img = Image.new("RGB", size, color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_upload_unterschrift_creates_event_with_url(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        f"/api/vorgaenge/{vorgang.id}/events/unterschrift",
        headers=auth_headers(token),
        files={"file": ("unterschrift.png", _make_test_image_bytes(), "image/png")},
        data={"unterzeichner_name": "Max Mustermann"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["event_type"] == "unterschrift"
    assert body["unterschrift_url"] is not None
    assert body["payload"]["unterzeichner_name"] == "Max Mustermann"
    assert body["kundensichtbar"] is True


@pytest.mark.asyncio
async def test_upload_unterschrift_ohne_namen_schlaegt_fehl(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        f"/api/vorgaenge/{vorgang.id}/events/unterschrift",
        headers=auth_headers(token),
        files={"file": ("unterschrift.png", _make_test_image_bytes(), "image/png")},
        data={"unterzeichner_name": "   "},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_unterschrift_rejects_non_image(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        f"/api/vorgaenge/{vorgang.id}/events/unterschrift",
        headers=auth_headers(token),
        files={"file": ("test.txt", b"not an image", "text/plain")},
        data={"unterzeichner_name": "Max Mustermann"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_unterschrift_erscheint_in_event_liste(
    client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")

    await client.post(
        f"/api/vorgaenge/{vorgang.id}/events/unterschrift",
        headers=auth_headers(token),
        files={"file": ("unterschrift.png", _make_test_image_bytes(), "image/png")},
        data={"unterzeichner_name": "Erika Musterfrau"},
    )

    events_resp = await client.get(
        f"/api/vorgaenge/{vorgang.id}/events", headers=auth_headers(token)
    )
    unterschrift_events = [e for e in events_resp.json() if e["event_type"] == "unterschrift"]
    assert len(unterschrift_events) == 1
    assert unterschrift_events[0]["unterschrift_url"] is not None
