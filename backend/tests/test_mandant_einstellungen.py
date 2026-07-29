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
