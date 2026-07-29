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
async def test_create_anlage_ohne_adresse(client, make_mandant, make_user, make_kunde):
    """Minimal-Anlage wie beim Inline-Formular in der Kunden-Profilseite/
    "Neuer Vorgang" -- nur Bezeichnung und optional ein Typ, keine Adresse."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/anlagen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "bezeichnung": "Wallbox Stellplatz 3"},
    )
    assert resp.status_code == 201
    assert resp.json()["adresse"] == {}


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


@pytest.mark.asyncio
async def test_qr_scan_finds_own_anlage(
    client, make_mandant, make_user, make_kunde, make_anlage, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde, qr_code="QR-SCAN-TEST-1")
    await make_kunde_zuweisung(mandant=mandant, kunde=kunde, techniker=techniker)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.get("/api/anlagen/by-qr/QR-SCAN-TEST-1", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["id"] == str(anlage.id)


@pytest.mark.asyncio
async def test_qr_scan_unknown_code_404(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.get("/api/anlagen/by-qr/DOES-NOT-EXIST", headers=auth_headers(token))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_qr_scan_does_not_leak_other_mandants_anlage(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    techniker_a = await make_user(mandant=mandant_a, role="techniker", password="pw-123456")
    kunde_b = await make_kunde(mandant=mandant_b)
    await make_anlage(mandant=mandant_b, kunde=kunde_b, qr_code="QR-FREMD-1")
    token = await login(client, techniker_a.email, "pw-123456")

    resp = await client.get("/api/anlagen/by-qr/QR-FREMD-1", headers=auth_headers(token))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_anlage_profil_auswertung(
    client, make_mandant, make_user, make_kunde, make_anlage, make_vorgang
):
    """AnlageProfil zaehlt Vorgaenge nach Status und summiert die erfasste
    Zeit -- ueber ALLE Vorgaenge der Anlage, nicht nur die (auf 50) begrenzte
    Liste."""
    from datetime import datetime, timedelta, timezone

    from app.db.session import system_session
    from app.models.zeiterfassung import Zeiterfassung

    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde)
    vorgang1 = await make_vorgang(mandant=mandant, kunde=kunde, anlage_id=anlage.id, status="neu")
    vorgang2 = await make_vorgang(
        mandant=mandant, kunde=kunde, anlage_id=anlage.id, status="abgeschlossen"
    )

    start = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    async with system_session() as session:
        session.add(
            Zeiterfassung(
                mandant_id=mandant.id,
                vorgang_id=vorgang1.id,
                techniker_id=techniker.id,
                start_at=start,
                ende_at=start + timedelta(hours=2, minutes=30),
            )
        )
        session.add(
            Zeiterfassung(
                mandant_id=mandant.id,
                vorgang_id=vorgang2.id,
                techniker_id=techniker.id,
                start_at=start,
                ende_at=start + timedelta(hours=1),
            )
        )
        await session.flush()

    token = await login(client, admin.email, "pw-123456")
    resp = await client.get(f"/api/anlagen/{anlage.id}/profil", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["vorgaenge_nach_status"] == {"neu": 1, "abgeschlossen": 1}
    assert body["zeiterfassung_stunden_gesamt"] == "3.5"


@pytest.mark.asyncio
async def test_vorgaenge_und_feed_filterbar_nach_anlage(
    client, make_mandant, make_user, make_kunde, make_anlage, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage1 = await make_anlage(mandant=mandant, kunde=kunde, bezeichnung="Anlage 1")
    anlage2 = await make_anlage(mandant=mandant, kunde=kunde, bezeichnung="Anlage 2")
    await make_vorgang(mandant=mandant, kunde=kunde, anlage_id=anlage1.id, titel="V-Anlage-1")
    await make_vorgang(mandant=mandant, kunde=kunde, anlage_id=anlage2.id, titel="V-Anlage-2")
    token = await login(client, admin.email, "pw-123456")

    vorgaenge_resp = await client.get(
        "/api/vorgaenge", headers=auth_headers(token), params={"anlage_id": str(anlage1.id)}
    )
    assert [v["titel"] for v in vorgaenge_resp.json()] == ["V-Anlage-1"]

    feed_resp = await client.get(
        "/api/feed", headers=auth_headers(token), params={"anlage_id": str(anlage1.id)}
    )
    assert [i["titel"] for i in feed_resp.json()["items"]] == ["V-Anlage-1"]
