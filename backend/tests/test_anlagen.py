import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_create_anlage_for_own_kunde(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/anlagen",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "bezeichnung": "Hauptverteilung Haus A",
            "adresse": {"strasse": "Musterweg 1", "ort": "Musterstadt"},
            "anlagentyp": "niederspannung",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["bezeichnung"] == "Hauptverteilung Haus A"


@pytest.mark.asyncio
async def test_cannot_create_anlage_for_foreign_kunde(
    client, make_mandant, make_user, make_kunde
):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    admin_a = await make_user(mandant=mandant_a, role="mandant_admin", password="pw-123456")
    kunde_b = await make_kunde(mandant=mandant_b)
    token = await login(client, admin_a.email, "pw-123456")

    resp = await client.post(
        "/api/anlagen",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde_b.id),
            "bezeichnung": "Fremde Anlage",
            "adresse": {"strasse": "X"},
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_qr_code_globally_unique(client, make_mandant, make_user, make_kunde):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    admin_a = await make_user(mandant=mandant_a, role="mandant_admin", password="pw-123456")
    admin_b = await make_user(mandant=mandant_b, role="mandant_admin", password="pw-123456")
    kunde_a = await make_kunde(mandant=mandant_a)
    kunde_b = await make_kunde(mandant=mandant_b)
    token_a = await login(client, admin_a.email, "pw-123456")
    token_b = await login(client, admin_b.email, "pw-123456")

    first = await client.post(
        "/api/anlagen",
        headers=auth_headers(token_a),
        json={"kunde_id": str(kunde_a.id), "bezeichnung": "A", "adresse": {}, "qr_code": "QR-1"},
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/anlagen",
        headers=auth_headers(token_b),
        json={"kunde_id": str(kunde_b.id), "bezeichnung": "B", "adresse": {}, "qr_code": "QR-1"},
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_list_anlagen_filtered_by_kunde(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde1 = await make_kunde(mandant=mandant, name="Kunde 1")
    kunde2 = await make_kunde(mandant=mandant, name="Kunde 2")
    await make_anlage(mandant=mandant, kunde=kunde1, bezeichnung="Anlage 1")
    await make_anlage(mandant=mandant, kunde=kunde2, bezeichnung="Anlage 2")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get(
        "/api/anlagen", headers=auth_headers(token), params={"kunde_id": str(kunde1.id)}
    )
    assert resp.status_code == 200
    assert [a["bezeichnung"] for a in resp.json()] == ["Anlage 1"]
