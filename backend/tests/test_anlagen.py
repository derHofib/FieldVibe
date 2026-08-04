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
async def test_anlage_universelle_beschreibungsfelder(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    create = await client.post(
        "/api/anlagen",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "bezeichnung": "Ladesäule Hof",
            "hersteller": "ABB",
            "modell": "Terra AC",
            "seriennummer": "SN-99",
            "anschaffungsdatum": "2025-03-01",
            "notiz": "Steht hinter dem Lager",
        },
    )
    assert create.status_code == 201
    body = create.json()
    assert body["hersteller"] == "ABB"
    assert body["modell"] == "Terra AC"
    assert body["seriennummer"] == "SN-99"
    assert body["anschaffungsdatum"] == "2025-03-01"
    assert body["notiz"] == "Steht hinter dem Lager"

    update = await client.patch(
        f"/api/anlagen/{body['id']}", headers=auth_headers(token), json={"hersteller": "Alfen"}
    )
    assert update.status_code == 200
    assert update.json()["hersteller"] == "Alfen"


@pytest.mark.asyncio
async def test_anlagen_feld_definitionen_crud(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    create = await client.post(
        "/api/anlagen-feld-definitionen",
        headers=auth_headers(token),
        json={"anlagentyp": "Fahrzeug", "feld_name": "Kennzeichen", "feld_typ": "text"},
    )
    assert create.status_code == 201
    definition_id = create.json()["id"]

    listed = await client.get(
        "/api/anlagen-feld-definitionen?anlagentyp=Fahrzeug", headers=auth_headers(token)
    )
    assert [f["feld_name"] for f in listed.json()] == ["Kennzeichen"]

    konflikt = await client.post(
        "/api/anlagen-feld-definitionen",
        headers=auth_headers(token),
        json={"anlagentyp": "Fahrzeug", "feld_name": "Kennzeichen", "feld_typ": "text"},
    )
    assert konflikt.status_code == 409

    update = await client.patch(
        f"/api/anlagen-feld-definitionen/{definition_id}",
        headers=auth_headers(token),
        json={"feld_typ": "zahl"},
    )
    assert update.status_code == 200
    assert update.json()["feld_typ"] == "zahl"

    delete = await client.delete(
        f"/api/anlagen-feld-definitionen/{definition_id}", headers=auth_headers(token)
    )
    assert delete.status_code == 204


@pytest.mark.asyncio
async def test_anlagen_feld_definition_nur_mandant_admin(client, make_mandant, make_user):
    mandant = await make_mandant()
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    token = await login(client, disponent.email, "pw-123456")

    resp = await client.post(
        "/api/anlagen-feld-definitionen",
        headers=auth_headers(token),
        json={"anlagentyp": "Fahrzeug", "feld_name": "Kennzeichen", "feld_typ": "text"},
    )
    assert resp.status_code == 403


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
async def test_admin_can_delete_unused_anlage(client, make_mandant, make_user, make_kunde, make_anlage):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.delete(f"/api/anlagen/{anlage.id}", headers=auth_headers(token))
    assert resp.status_code == 204

    get_resp = await client.get(f"/api/anlagen/{anlage.id}", headers=auth_headers(token))
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_anlage_delete_blocked_when_vorgang_exists(
    client, make_mandant, make_user, make_kunde, make_anlage, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde)
    await make_vorgang(mandant=mandant, kunde=kunde, anlage_id=anlage.id)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.delete(f"/api/anlagen/{anlage.id}", headers=auth_headers(token))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_techniker_cannot_delete_anlage(client, make_mandant, make_user, make_kunde, make_anlage):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.delete(f"/api/anlagen/{anlage.id}", headers=auth_headers(token))
    assert resp.status_code == 403


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
async def test_fahrzeug_anlage_ohne_kunde_anlegen(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/anlagen",
        headers=auth_headers(token),
        json={"objekttyp": "fahrzeug", "bezeichnung": "Transporter VW"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["objekttyp"] == "fahrzeug"
    assert body["kunde_id"] is None


@pytest.mark.asyncio
async def test_kundenanlage_ohne_kunde_id_schlaegt_fehl(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/anlagen",
        headers=auth_headers(token),
        json={"bezeichnung": "Anlage ohne Kunde"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_fahrzeug_mit_kunde_id_schlaegt_fehl(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/anlagen",
        headers=auth_headers(token),
        json={"objekttyp": "fahrzeug", "bezeichnung": "Transporter", "kunde_id": str(kunde.id)},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_techniker_sieht_fahrzeuge_ohne_kunde_zuweisung(
    client, make_mandant, make_user, make_anlage
):
    """Interne Objekte (Fahrzeuge/Lager) sind keine Kundendaten -- ein
    Techniker ohne jede Kunde-Zuweisung sieht sie trotzdem."""
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter")
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.get("/api/anlagen", headers=auth_headers(token))
    assert resp.status_code == 200
    bezeichnungen = [a["bezeichnung"] for a in resp.json()]
    assert fahrzeug.bezeichnung in bezeichnungen
    assert "Zentrallager" in bezeichnungen

    get_resp = await client.get(f"/api/anlagen/{fahrzeug.id}", headers=auth_headers(token))
    assert get_resp.status_code == 200


@pytest.mark.asyncio
async def test_liste_filterbar_nach_objekttyp(client, make_mandant, make_user, make_kunde, make_anlage):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    await make_anlage(mandant=mandant, kunde=kunde, bezeichnung="Kundenanlage")
    await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Fahrzeug 1")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/anlagen", headers=auth_headers(token), params={"objekttyp": "fahrzeug"})
    assert resp.status_code == 200
    assert [a["bezeichnung"] for a in resp.json()] == ["Fahrzeug 1"]


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
