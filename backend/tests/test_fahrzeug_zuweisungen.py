import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_admin_kann_fahrzeug_zuweisen(client, make_mandant, make_user, make_anlage):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.put(
        f"/api/fahrzeug-zuweisungen/{techniker.id}",
        headers=auth_headers(token),
        json={"anlage_id": str(fahrzeug.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == str(fahrzeug.id)

    techniker_token = await login(client, techniker.email, "pw-123456")
    mir_resp = await client.get("/api/fahrzeug-zuweisungen/mir", headers=auth_headers(techniker_token))
    assert mir_resp.status_code == 200
    assert mir_resp.json()["id"] == str(fahrzeug.id)


@pytest.mark.asyncio
async def test_zuweisung_kann_geaendert_werden(client, make_mandant, make_user, make_anlage):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    fahrzeug1 = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter 1")
    fahrzeug2 = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter 2")
    token = await login(client, admin.email, "pw-123456")

    await client.put(
        f"/api/fahrzeug-zuweisungen/{techniker.id}",
        headers=auth_headers(token),
        json={"anlage_id": str(fahrzeug1.id)},
    )
    resp = await client.put(
        f"/api/fahrzeug-zuweisungen/{techniker.id}",
        headers=auth_headers(token),
        json={"anlage_id": str(fahrzeug2.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == str(fahrzeug2.id)


@pytest.mark.asyncio
async def test_zuweisung_kann_entfernt_werden(client, make_mandant, make_user, make_anlage):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter")
    token = await login(client, admin.email, "pw-123456")

    await client.put(
        f"/api/fahrzeug-zuweisungen/{techniker.id}",
        headers=auth_headers(token),
        json={"anlage_id": str(fahrzeug.id)},
    )
    resp = await client.put(
        f"/api/fahrzeug-zuweisungen/{techniker.id}",
        headers=auth_headers(token),
        json={"anlage_id": None},
    )
    assert resp.status_code == 200
    assert resp.json() is None

    techniker_token = await login(client, techniker.email, "pw-123456")
    mir_resp = await client.get("/api/fahrzeug-zuweisungen/mir", headers=auth_headers(techniker_token))
    assert mir_resp.json() is None


@pytest.mark.asyncio
async def test_kundenanlage_darf_nicht_als_fahrzeug_zugewiesen_werden(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    kundenanlage = await make_anlage(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.put(
        f"/api/fahrzeug-zuweisungen/{techniker.id}",
        headers=auth_headers(token),
        json={"anlage_id": str(kundenanlage.id)},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_techniker_darf_keine_zuweisung_setzen(client, make_mandant, make_user, make_anlage):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter")
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.put(
        f"/api/fahrzeug-zuweisungen/{techniker.id}",
        headers=auth_headers(token),
        json={"anlage_id": str(fahrzeug.id)},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_uebersicht_zeigt_auch_technikers_ohne_zuweisung(
    client, make_mandant, make_user, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    techniker_mit = await make_user(
        mandant=mandant, role="techniker", password="pw-123456", name="Mit Fahrzeug"
    )
    techniker_ohne = await make_user(
        mandant=mandant, role="techniker", password="pw-123456", name="Ohne Fahrzeug"
    )
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter")
    token = await login(client, admin.email, "pw-123456")

    await client.put(
        f"/api/fahrzeug-zuweisungen/{techniker_mit.id}",
        headers=auth_headers(token),
        json={"anlage_id": str(fahrzeug.id)},
    )

    resp = await client.get("/api/fahrzeug-zuweisungen", headers=auth_headers(token))
    assert resp.status_code == 200
    by_name = {row["techniker"]["name"]: row["fahrzeug"] for row in resp.json()}
    assert by_name["Mit Fahrzeug"]["id"] == str(fahrzeug.id)
    assert by_name["Ohne Fahrzeug"] is None
