import io

import pytest
from PIL import Image

from tests.conftest import auth_headers, login


def _make_test_image_bytes(size=(400, 300)) -> bytes:
    img = Image.new("RGB", size, color=(80, 140, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_board_crud(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    create = await client.post(
        "/api/boards",
        headers=auth_headers(token),
        json={"name": "Projektplanung Rheinblick", "board_typ": "frei", "inhalt_json": {"nodes": []}},
    )
    assert create.status_code == 201
    body = create.json()
    board_id = body["id"]
    assert body["board_typ"] == "frei"
    assert body["inhalt_json"] == {"nodes": []}

    listed = await client.get("/api/boards", headers=auth_headers(token))
    assert listed.status_code == 200
    assert [b["name"] for b in listed.json()] == ["Projektplanung Rheinblick"]
    # Uebersicht liefert bewusst kein inhalt_json.
    assert "inhalt_json" not in listed.json()[0]

    got = await client.get(f"/api/boards/{board_id}", headers=auth_headers(token))
    assert got.status_code == 200
    assert got.json()["inhalt_json"] == {"nodes": []}

    update = await client.patch(
        f"/api/boards/{board_id}",
        headers=auth_headers(token),
        json={"inhalt_json": {"nodes": [{"id": "n1", "type": "sticky"}]}},
    )
    assert update.status_code == 200
    assert update.json()["inhalt_json"]["nodes"][0]["id"] == "n1"

    delete = await client.delete(f"/api/boards/{board_id}", headers=auth_headers(token))
    assert delete.status_code == 204
    listed_after = await client.get("/api/boards", headers=auth_headers(token))
    assert listed_after.json() == []


@pytest.mark.asyncio
async def test_board_rls_isolation_zwischen_mandanten(client, make_mandant, make_user):
    mandant_a = await make_mandant()
    mandant_b = await make_mandant()
    admin_a = await make_user(mandant=mandant_a, role="mandant_admin", password="pw-123456", email="a@a.de")
    admin_b = await make_user(mandant=mandant_b, role="mandant_admin", password="pw-123456", email="b@b.de")
    token_a = await login(client, admin_a.email, "pw-123456")
    token_b = await login(client, admin_b.email, "pw-123456")

    create = await client.post(
        "/api/boards",
        headers=auth_headers(token_a),
        json={"name": "Nur Mandant A", "board_typ": "frei"},
    )
    board_id = create.json()["id"]

    listed_b = await client.get("/api/boards", headers=auth_headers(token_b))
    assert listed_b.json() == []

    get_b = await client.get(f"/api/boards/{board_id}", headers=auth_headers(token_b))
    assert get_b.status_code == 404

    delete_b = await client.delete(f"/api/boards/{board_id}", headers=auth_headers(token_b))
    assert delete_b.status_code == 404


@pytest.mark.asyncio
async def test_board_hintergrund_upload_und_url(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    create = await client.post(
        "/api/boards",
        headers=auth_headers(token),
        json={"name": "E-Check Hauptverteilung", "board_typ": "bauplanung"},
    )
    board_id = create.json()["id"]

    leer = await client.get(f"/api/boards/{board_id}/hintergrund-url", headers=auth_headers(token))
    assert leer.json() == {"url": None}

    upload = await client.post(
        f"/api/boards/{board_id}/hintergrund",
        headers=auth_headers(token),
        files={"file": ("grundriss.png", _make_test_image_bytes(), "image/png")},
    )
    assert upload.status_code == 200
    assert upload.json()["hintergrund_object_key"] is not None

    mit_url = await client.get(f"/api/boards/{board_id}/hintergrund-url", headers=auth_headers(token))
    assert mit_url.json()["url"] is not None

    abgelehnt = await client.post(
        f"/api/boards/{board_id}/hintergrund",
        headers=auth_headers(token),
        files={"file": ("plan.txt", b"kein bild", "text/plain")},
    )
    assert abgelehnt.status_code == 400

    entfernt = await client.delete(f"/api/boards/{board_id}/hintergrund", headers=auth_headers(token))
    assert entfernt.status_code == 200
    assert entfernt.json()["hintergrund_object_key"] is None
