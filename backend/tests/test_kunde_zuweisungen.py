import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_techniker_without_zuweisung_sieht_kunde_nicht(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, techniker.email, "pw-123456")

    assert (await client.get(f"/api/kunden/{kunde.id}", headers=auth_headers(token))).status_code == 404
    assert (await client.get("/api/kunden", headers=auth_headers(token))).json() == []
    assert (
        await client.get(f"/api/vorgaenge/{vorgang.id}", headers=auth_headers(token))
    ).status_code == 404
    assert (await client.get("/api/vorgaenge", headers=auth_headers(token))).json() == []
    feed = await client.get("/api/feed", headers=auth_headers(token))
    assert feed.json()["items"] == []
    search = await client.get("/api/search", headers=auth_headers(token), params={"q": kunde.name})
    assert search.json()["treffer"] == []


@pytest.mark.asyncio
async def test_mandant_admin_kann_techniker_zuweisen_und_techniker_sieht_dann_kunde(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    admin_token = await login(client, admin.email, "pw-123456")

    resp = await client.put(
        f"/api/kunden/{kunde.id}/techniker",
        headers=auth_headers(admin_token),
        json={"user_ids": [str(techniker.id)]},
    )
    assert resp.status_code == 200
    assert [t["id"] for t in resp.json()] == [str(techniker.id)]

    techniker_token = await login(client, techniker.email, "pw-123456")
    assert (
        await client.get(f"/api/kunden/{kunde.id}", headers=auth_headers(techniker_token))
    ).status_code == 200
    assert (
        await client.get(f"/api/vorgaenge/{vorgang.id}", headers=auth_headers(techniker_token))
    ).status_code == 200
    kunden_liste = await client.get("/api/kunden", headers=auth_headers(techniker_token))
    assert [k["id"] for k in kunden_liste.json()] == [str(kunde.id)]

    profil = await client.get(f"/api/kunden/{kunde.id}/profil", headers=auth_headers(admin_token))
    assert [t["id"] for t in profil.json()["techniker"]] == [str(techniker.id)]


@pytest.mark.asyncio
async def test_zuweisung_kann_wieder_entfernt_werden(
    client, make_mandant, make_user, make_kunde, make_kunde_zuweisung
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    admin_token = await login(client, admin.email, "pw-123456")
    techniker_token = await login(client, techniker.email, "pw-123456")

    assert (
        await client.get(f"/api/kunden/{kunde.id}", headers=auth_headers(techniker_token))
    ).status_code == 200

    resp = await client.put(
        f"/api/kunden/{kunde.id}/techniker",
        headers=auth_headers(admin_token),
        json={"user_ids": []},
    )
    assert resp.status_code == 200
    assert resp.json() == []

    assert (
        await client.get(f"/api/kunden/{kunde.id}", headers=auth_headers(techniker_token))
    ).status_code == 404


@pytest.mark.asyncio
async def test_disponent_und_mandant_admin_sehen_alle_kunden_unabhaengig_von_zuweisung(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)

    for user in (admin, disponent):
        token = await login(client, user.email, "pw-123456")
        resp = await client.get(f"/api/kunden/{kunde.id}", headers=auth_headers(token))
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_zuweisung_lehnt_fremden_oder_falschen_user_ab(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    mandant_fremd = await make_mandant(name="Fremdbetrieb")
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    techniker_fremd = await make_user(mandant=mandant_fremd, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp_fremd = await client.put(
        f"/api/kunden/{kunde.id}/techniker",
        headers=auth_headers(token),
        json={"user_ids": [str(techniker_fremd.id)]},
    )
    assert resp_fremd.status_code == 400

    resp_falsche_rolle = await client.put(
        f"/api/kunden/{kunde.id}/techniker",
        headers=auth_headers(token),
        json={"user_ids": [str(disponent.id)]},
    )
    assert resp_falsche_rolle.status_code == 400


@pytest.mark.asyncio
async def test_techniker_darf_zuweisungen_nicht_selbst_verwalten(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.put(
        f"/api/kunden/{kunde.id}/techniker",
        headers=auth_headers(token),
        json={"user_ids": [str(techniker.id)]},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_uebersicht_zeigt_techniker_mit_und_ohne_kunden(
    client, make_mandant, make_user, make_kunde, make_kunde_zuweisung
):
    mandant = await make_mandant()
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    tech_mit_kunde = await make_user(
        mandant=mandant, role="techniker", password="pw-123456", name="Mit Kunde"
    )
    tech_ohne_kunde = await make_user(
        mandant=mandant, role="techniker", password="pw-123456", name="Ohne Kunde"
    )
    kunde = await make_kunde(mandant=mandant)
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=tech_mit_kunde)
    token = await login(client, disponent.email, "pw-123456")

    resp = await client.get("/api/techniker-zuweisungen", headers=auth_headers(token))
    assert resp.status_code == 200
    by_id = {row["techniker"]["id"]: row["kunden"] for row in resp.json()}
    assert [k["id"] for k in by_id[str(tech_mit_kunde.id)]] == [str(kunde.id)]
    assert by_id[str(tech_ohne_kunde.id)] == []


@pytest.mark.asyncio
async def test_techniker_kann_keinen_vorgang_fuer_fremden_kunden_anlegen(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/vorgaenge",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "titel": "Sollte scheitern",
            "abrechnungsart": "aufwand",
            "leistungstyp": "stoerung",
        },
    )
    assert resp.status_code == 403
