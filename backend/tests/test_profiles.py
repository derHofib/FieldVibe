import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_kunde_profil_includes_anlagen_und_vorgaenge(
    client, make_mandant, make_user, make_kunde, make_anlage, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, name="Profil-Kunde")
    anlage = await make_anlage(mandant=mandant, kunde=kunde)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, titel="Profil-Vorgang")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get(f"/api/kunden/{kunde.id}/profil", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Profil-Kunde"
    assert [a["id"] for a in body["anlagen"]] == [str(anlage.id)]
    assert [v["id"] for v in body["vorgaenge"]] == [str(vorgang.id)]
    assert body["tags"] == []


@pytest.mark.asyncio
async def test_anlage_profil_includes_kunde_und_vorgaenge(
    client, make_mandant, make_user, make_kunde, make_anlage, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, name="Kunde der Anlage")
    anlage = await make_anlage(mandant=mandant, kunde=kunde, bezeichnung="Profil-Anlage")
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, anlage_id=anlage.id)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get(f"/api/anlagen/{anlage.id}/profil", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["bezeichnung"] == "Profil-Anlage"
    assert body["kunde"]["name"] == "Kunde der Anlage"
    assert [v["id"] for v in body["vorgaenge"]] == [str(vorgang.id)]


@pytest.mark.asyncio
async def test_kunde_profil_manipulated_id_across_tenants_404(
    client, make_mandant, make_user, make_kunde
):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    admin_a = await make_user(mandant=mandant_a, role="mandant_admin", password="pw-123456")
    kunde_b = await make_kunde(mandant=mandant_b)
    token = await login(client, admin_a.email, "pw-123456")

    resp = await client.get(f"/api/kunden/{kunde_b.id}/profil", headers=auth_headers(token))
    assert resp.status_code == 404
