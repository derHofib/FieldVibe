import io

import pytest
from PIL import Image

from tests.conftest import auth_headers, login


def _make_test_image_bytes(size=(600, 600)) -> bytes:
    img = Image.new("RGB", size, color=(120, 200, 80))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_upload_foto_creates_event_with_urls(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        f"/api/vorgaenge/{vorgang.id}/events/foto",
        headers=auth_headers(token),
        files={"file": ("test.jpg", _make_test_image_bytes(), "image/jpeg")},
        data={"kundensichtbar": "true", "body": "Schadensbild"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["event_type"] == "foto"
    assert body["kundensichtbar"] is True
    assert body["foto_url"] is not None
    assert body["foto_thumbnail_url"] is not None
    assert body["payload"]["size"] > 0


@pytest.mark.asyncio
async def test_upload_rejects_non_image(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        f"/api/vorgaenge/{vorgang.id}/events/foto",
        headers=auth_headers(token),
        files={"file": ("test.txt", b"not an image", "text/plain")},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_uploaded_foto_appears_in_event_list(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, techniker.email, "pw-123456")

    await client.post(
        f"/api/vorgaenge/{vorgang.id}/events/foto",
        headers=auth_headers(token),
        files={"file": ("test.jpg", _make_test_image_bytes(), "image/jpeg")},
    )

    events_resp = await client.get(
        f"/api/vorgaenge/{vorgang.id}/events", headers=auth_headers(token)
    )
    foto_events = [e for e in events_resp.json() if e["event_type"] == "foto"]
    assert len(foto_events) == 1
    assert foto_events[0]["foto_url"] is not None


@pytest.mark.asyncio
async def test_upload_foto_for_unknown_vorgang_404(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/vorgaenge/00000000-0000-0000-0000-000000000000/events/foto",
        headers=auth_headers(token),
        files={"file": ("test.jpg", _make_test_image_bytes(), "image/jpeg")},
    )
    assert resp.status_code == 404
