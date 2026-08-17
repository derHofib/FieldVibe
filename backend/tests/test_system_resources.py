import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_super_admin_sieht_aktuelle_werte_und_verlauf(client, make_user):
    super_admin = await make_user(mandant=None, role="super_admin", password="pw-123456")
    token = await login(client, super_admin.email, "pw-123456")

    resp = await client.get("/api/admin/system/resources", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()

    aktuell = body["aktuell"]
    for feld in ("cpu_percent", "ram_percent", "ram_used_mb", "ram_total_mb", "disk_percent", "disk_used_gb", "disk_total_gb"):
        assert feld in aktuell
    assert 0 <= aktuell["cpu_percent"] <= 100
    assert 0 <= aktuell["ram_percent"] <= 100
    assert aktuell["ram_used_mb"] <= aktuell["ram_total_mb"]
    assert isinstance(body["verlauf"], list)


@pytest.mark.asyncio
async def test_mandant_admin_hat_keinen_zugriff(client, make_mandant, make_user):
    mandant = await make_mandant(name="Elektro Beispiel")
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/admin/system/resources", headers=auth_headers(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_techniker_hat_keinen_zugriff(client, make_mandant, make_user):
    mandant = await make_mandant(name="Elektro Beispiel 2")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.get("/api/admin/system/resources", headers=auth_headers(token))
    assert resp.status_code == 403
