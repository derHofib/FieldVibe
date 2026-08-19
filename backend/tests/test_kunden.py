import pytest

from tests.conftest import auth_headers, login


async def _extrahiere_token(link: str) -> str:
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(link).query)["token"][0]


@pytest.mark.asyncio
async def test_disponent_can_create_and_list_kunden(client, make_mandant, make_user):
    mandant = await make_mandant()
    disponent = await make_user(mandant=mandant, role="disponent", password="pw-123456")
    token = await login(client, disponent.email, "pw-123456")

    resp = await client.post(
        "/api/kunden",
        headers=auth_headers(token),
        json={"name": "Müller Immobilien GmbH", "typ": "gewerbe"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["kundennummer"] == "K-00001"

    list_resp = await client.get("/api/kunden", headers=auth_headers(token))
    assert list_resp.status_code == 200
    assert any(k["name"] == "Müller Immobilien GmbH" for k in list_resp.json())


@pytest.mark.asyncio
async def test_kundennummer_auto_increments_per_mandant(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    first = await client.post(
        "/api/kunden", headers=auth_headers(token), json={"name": "Kunde A"}
    )
    second = await client.post(
        "/api/kunden", headers=auth_headers(token), json={"name": "Kunde B"}
    )
    assert first.json()["kundennummer"] == "K-00001"
    assert second.json()["kundennummer"] == "K-00002"


@pytest.mark.asyncio
async def test_techniker_can_read_but_not_create_kunden(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    list_resp = await client.get("/api/kunden", headers=auth_headers(token))
    assert list_resp.status_code == 200

    create_resp = await client.post(
        "/api/kunden", headers=auth_headers(token), json={"name": "Verboten GmbH"}
    )
    assert create_resp.status_code == 403


@pytest.mark.asyncio
async def test_duplicate_kundennummer_conflicts(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    payload = {"name": "Kunde A", "kundennummer": "MANUELL-1"}
    first = await client.post("/api/kunden", headers=auth_headers(token), json=payload)
    assert first.status_code == 201

    second = await client.post(
        "/api/kunden",
        headers=auth_headers(token),
        json={"name": "Kunde B", "kundennummer": "MANUELL-1"},
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_kunde_update(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/kunden/{kunde.id}", headers=auth_headers(token), json={"notiz": "Wichtiger Kunde"}
    )
    assert resp.status_code == 200
    assert resp.json()["notiz"] == "Wichtiger Kunde"


@pytest.mark.asyncio
async def test_kunde_create_mit_adresse_und_ansprechpartner(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/kunden",
        headers=auth_headers(token),
        json={
            "name": "Bäckerei Sonnenschein",
            "typ": "gewerbe",
            "adresse": {"strasse": "Hauptstr. 1", "plz": "12345", "ort": "Musterstadt"},
            "ansprechpartner": [
                {
                    "name": "Erika Musterfrau",
                    "position": "Geschäftsführerin",
                    "telefon": "0170-1234567",
                    "email": "erika@baeckerei-sonnenschein.de",
                    "operativ": False,
                    "eskalationsstufe": 3,
                }
            ],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["adresse"] == {"strasse": "Hauptstr. 1", "plz": "12345", "ort": "Musterstadt"}
    assert len(body["ansprechpartner"]) == 1
    ansprechpartner = body["ansprechpartner"][0]
    assert ansprechpartner["name"] == "Erika Musterfrau"
    assert ansprechpartner["eskalationsstufe"] == 3
    assert ansprechpartner["operativ"] is False
    assert "id" in ansprechpartner


@pytest.mark.asyncio
async def test_kunde_ansprechpartner_eskalationsstufe_ausserhalb_bereich_schlaegt_fehl(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/kunden",
        headers=auth_headers(token),
        json={
            "name": "Kunde A",
            "ansprechpartner": [{"name": "Max Mustermann", "eskalationsstufe": 5}],
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_kunde_update_ansprechpartner_liste(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/kunden/{kunde.id}",
        headers=auth_headers(token),
        json={
            "ansprechpartner": [
                {"name": "Hans Meier", "position": "Hausmeister", "operativ": True, "eskalationsstufe": 1}
            ]
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["ansprechpartner"]) == 1
    assert body["ansprechpartner"][0]["operativ"] is True

    # Erneut lesen bestaetigt, dass die Liste tatsaechlich persistiert wurde
    # (nicht nur in der Response-Serialisierung des PATCH-Aufrufs korrekt ist).
    get_resp = await client.get(f"/api/kunden/{kunde.id}", headers=auth_headers(token))
    assert get_resp.json()["ansprechpartner"][0]["name"] == "Hans Meier"


@pytest.mark.asyncio
async def test_admin_can_delete_unused_kunde(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.delete(f"/api/kunden/{kunde.id}", headers=auth_headers(token))
    assert resp.status_code == 204

    get_resp = await client.get(f"/api/kunden/{kunde.id}", headers=auth_headers(token))
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_kunde_delete_kaskadiert_auf_vorgang(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    # Papierkorb (siehe app/services/papierkorb_service.py): ein Kunde mit
    # abhaengigen Vorgaengen laesst sich loeschen -- die Loeschung kaskadiert
    # weich auf den Vorgang statt geblockt zu werden (siehe tests/test_papierkorb.py
    # fuer die vollstaendige Kaskade und das Wiederherstellen).
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.delete(f"/api/kunden/{kunde.id}", headers=auth_headers(token))
    assert resp.status_code == 204

    get_resp = await client.get(f"/api/kunden/{kunde.id}", headers=auth_headers(token))
    assert get_resp.status_code == 404
    vorgang_resp = await client.get(f"/api/vorgaenge/{vorgang.id}", headers=auth_headers(token))
    assert vorgang_resp.status_code == 404


@pytest.mark.asyncio
async def test_techniker_cannot_delete_kunde(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.delete(f"/api/kunden/{kunde.id}", headers=auth_headers(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unknown_kunde_returns_404(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get(
        "/api/kunden/00000000-0000-0000-0000-000000000000", headers=auth_headers(token)
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_datenexport_enthaelt_alle_personenbezogenen_daten(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    # Auskunftsersuchen/Datenuebertragbarkeit (Art. 15/20 DSGVO): der Export
    # muss Stammdaten, Vorgaenge mit Ereignissen, Rechnungen/Angebote und
    # Kundenportal-Zugaenge (ohne Passwort-Hash) enthalten.
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    kunde = await make_kunde(mandant=mandant, name="Export-Kunde")
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)

    event_resp = await client.post(
        f"/api/vorgaenge/{vorgang.id}/events",
        headers=auth_headers(token),
        json={"event_type": "kommentar", "body": "Testkommentar"},
    )
    assert event_resp.status_code == 201

    rechnung_resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "vorgang_id": str(vorgang.id), "betrag_netto": "100.00"},
    )
    assert rechnung_resp.status_code == 201

    einladung_resp = await client.post(
        f"/api/kunden/{kunde.id}/einladungen",
        headers=auth_headers(token),
        json={"email": "export-kunde@example.de"},
    )
    assert einladung_resp.status_code == 201
    reg_token = await _extrahiere_token(einladung_resp.json()["registrierungslink"])
    portal_resp = await client.post(
        "/api/kundenportal/auth/registrieren",
        json={"token": reg_token, "name": "Export Kunde", "password": "pw-1234567890"},
    )
    assert portal_resp.status_code == 201

    resp = await client.get(f"/api/kunden/{kunde.id}/datenexport", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()

    assert body["kunde"]["name"] == "Export-Kunde"
    assert len(body["vorgaenge"]) == 1
    assert body["vorgaenge"][0]["id"] == str(vorgang.id)
    assert any(e["body"] == "Testkommentar" for e in body["vorgaenge"][0]["ereignisse"])
    assert len(body["rechnungen"]) == 1
    assert len(body["kundenportal_zugaenge"]) == 1
    assert body["kundenportal_zugaenge"][0]["email"] == "export-kunde@example.de"
    assert "password_hash" not in body["kundenportal_zugaenge"][0]


@pytest.mark.asyncio
async def test_techniker_ohne_zuweisung_cannot_export_daten(
    client, make_mandant, make_user, make_kunde
):
    # techniker ist per Account-Typ auf zugewiesene Kunden beschraenkt (siehe
    # rechte_service.ist_auf_zugewiesene_kunden_beschraenkt) -- ein nicht
    # zugewiesener Kunde liefert wie ueberall sonst 404 statt 403, um dessen
    # Existenz nicht zu verraten.
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.get(f"/api/kunden/{kunde.id}/datenexport", headers=auth_headers(token))
    assert resp.status_code == 404
