import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_default_effektive_stunde_ohne_eigene_konfiguration(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/mandant/einstellungen", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["scheduler_stunde_utc"] is None
    assert body["effektive_scheduler_stunde_utc"] == 3


@pytest.mark.asyncio
async def test_admin_kann_eigene_stunde_setzen_und_zuruecksetzen(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    set_resp = await client.patch(
        "/api/mandant/einstellungen", headers=auth_headers(token), json={"scheduler_stunde_utc": 22}
    )
    assert set_resp.status_code == 200
    body = set_resp.json()
    assert body["scheduler_stunde_utc"] == 22
    assert body["effektive_scheduler_stunde_utc"] == 22

    reset_resp = await client.patch(
        "/api/mandant/einstellungen", headers=auth_headers(token), json={"scheduler_stunde_utc": None}
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["scheduler_stunde_utc"] is None
    assert reset_resp.json()["effektive_scheduler_stunde_utc"] == 3


@pytest.mark.asyncio
async def test_stunde_ausserhalb_0_bis_23_wird_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        "/api/mandant/einstellungen", headers=auth_headers(token), json={"scheduler_stunde_utc": 24}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_non_admin_cannot_access_einstellungen(client, make_mandant, make_user):
    mandant = await make_mandant()
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    token = await login(client, disponent.email, "pw-123456")

    resp = await client.get("/api/mandant/einstellungen", headers=auth_headers(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_mandant_isolation_for_einstellungen(client, make_mandant, make_user):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    admin1 = await make_user(mandant=mandant1, role="mandant_admin", password="pw-123456")
    admin2 = await make_user(mandant=mandant2, role="mandant_admin", password="pw-123456")
    token1 = await login(client, admin1.email, "pw-123456")
    token2 = await login(client, admin2.email, "pw-123456")

    await client.patch(
        "/api/mandant/einstellungen", headers=auth_headers(token1), json={"scheduler_stunde_utc": 10}
    )

    resp2 = await client.get("/api/mandant/einstellungen", headers=auth_headers(token2))
    assert resp2.json()["scheduler_stunde_utc"] is None


@pytest.mark.asyncio
async def test_default_firmendaten_ist_leer(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/mandant/einstellungen", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["firmendaten"] == {}
    assert body["logo_object_key"] is None


@pytest.mark.asyncio
async def test_admin_kann_firmendaten_speichern(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    firmendaten = {
        "adresse": {"strasse": "Lange Str. 2", "plz": "10245", "ort": "Berlin"},
        "telefon": "+49 30 2121356",
        "email": "mail@muster.de",
        "iban": "DE10 2505 0500 5005 05",
    }
    resp = await client.patch(
        "/api/mandant/einstellungen", headers=auth_headers(token), json={"firmendaten": firmendaten}
    )
    assert resp.status_code == 200
    assert resp.json()["firmendaten"] == firmendaten

    verlauf = await client.get("/api/mandant/einstellungen", headers=auth_headers(token))
    assert verlauf.json()["firmendaten"] == firmendaten


@pytest.mark.asyncio
async def test_firmendaten_speichern_lasst_scheduler_stunde_unangetastet(
    client, make_mandant, make_user
):
    """Regressionstest: ein PATCH, der nur firmendaten mitschickt, darf eine
    zuvor gesetzte scheduler_stunde_utc nicht auf den globalen Default
    zuruecksetzen (siehe exclude_unset-Fix in mandant_einstellungen.py)."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    await client.patch(
        "/api/mandant/einstellungen", headers=auth_headers(token), json={"scheduler_stunde_utc": 21}
    )

    resp = await client.patch(
        "/api/mandant/einstellungen",
        headers=auth_headers(token),
        json={"firmendaten": {"telefon": "+49 30 1234567"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["scheduler_stunde_utc"] == 21
    assert body["firmendaten"]["telefon"] == "+49 30 1234567"


@pytest.mark.asyncio
async def test_mandant_admin_kann_logo_hochladen_und_entfernen(client, make_mandant, make_user):
    import io

    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    admin_token = await login(client, admin.email, "pw-123456")
    disponent_token = await login(client, disponent.email, "pw-123456")

    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
        b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    verboten = await client.post(
        "/api/mandant/einstellungen/logo",
        headers=auth_headers(disponent_token),
        files={"file": ("logo.png", io.BytesIO(png_bytes), "image/png")},
    )
    assert verboten.status_code == 403

    upload = await client.post(
        "/api/mandant/einstellungen/logo",
        headers=auth_headers(admin_token),
        files={"file": ("logo.png", io.BytesIO(png_bytes), "image/png")},
    )
    assert upload.status_code == 200
    assert upload.json()["logo_object_key"] is not None

    url_resp = await client.get(
        "/api/mandant/einstellungen/logo-url", headers=auth_headers(admin_token)
    )
    assert url_resp.status_code == 200
    assert url_resp.json()["url"] is not None

    remove_resp = await client.delete(
        "/api/mandant/einstellungen/logo", headers=auth_headers(admin_token)
    )
    assert remove_resp.status_code == 200
    assert remove_resp.json()["logo_object_key"] is None
