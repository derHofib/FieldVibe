import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_mandant_admin_can_create_vertrag(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/vertraege",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "bezeichnung": "Wartungsvertrag Premium",
            "abrechnungsart": "wartungsvertrag",
            "konditionen": {"stundensatz": 95.0},
        },
    )
    assert resp.status_code == 201
    assert resp.json()["konditionen"]["stundensatz"] == 95.0


@pytest.mark.asyncio
async def test_disponent_cannot_access_vertraege(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, disponent.email, "pw-123456")

    list_resp = await client.get("/api/vertraege", headers=auth_headers(token))
    assert list_resp.status_code == 403

    create_resp = await client.post(
        "/api/vertraege",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "bezeichnung": "Verboten",
            "abrechnungsart": "pauschale",
        },
    )
    assert create_resp.status_code == 403


@pytest.mark.asyncio
async def test_techniker_cannot_access_vertraege(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.get("/api/vertraege", headers=auth_headers(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_vertrag_deactivate(client, make_mandant, make_user, make_kunde, make_vertrag):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vertrag = await make_vertrag(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/vertraege/{vertrag.id}", headers=auth_headers(token), json={"aktiv": False}
    )
    assert resp.status_code == 200
    assert resp.json()["aktiv"] is False


@pytest.mark.asyncio
async def test_anlage_muss_zum_kunden_gehoeren_bei_create(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, name="Vertragskunde")
    fremder_kunde = await make_kunde(mandant=mandant, name="Fremder Kunde")
    fremde_anlage = await make_anlage(mandant=mandant, kunde=fremder_kunde)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/vertraege",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "anlage_id": str(fremde_anlage.id),
            "bezeichnung": "Sollte scheitern",
            "abrechnungsart": "pauschale",
        },
    )
    assert resp.status_code == 400
