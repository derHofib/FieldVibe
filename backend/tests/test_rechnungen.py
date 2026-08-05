import pytest

from app.db.session import system_session
from app.models.vorgang import Vorgang
from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_create_rechnung(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "betrag_netto": "200.00"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "entwurf"
    assert body["betrag_brutto"] == "238.00"
    assert body["rechnungsnummer"].startswith("R-")


@pytest.mark.asyncio
async def test_rechnung_leistungsdatum_wird_gespeichert(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "betrag_netto": "100", "leistungsdatum": "2026-07-15"},
    )
    assert resp.status_code == 201
    assert resp.json()["leistungsdatum"] == "2026-07-15"

    rechnung_id = resp.json()["id"]
    patched = await client.patch(
        f"/api/rechnungen/{rechnung_id}",
        headers=auth_headers(token),
        json={"leistungsdatum": "2026-07-20"},
    )
    assert patched.status_code == 200
    assert patched.json()["leistungsdatum"] == "2026-07-20"


@pytest.mark.asyncio
async def test_kleinunternehmer_erzwingt_null_prozent_mwst(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    settings_resp = await client.patch(
        "/api/mandant/einstellungen",
        headers=auth_headers(token),
        json={"firmendaten": {"ist_kleinunternehmer": True, "steuernummer": "12/345/67890"}},
    )
    assert settings_resp.status_code == 200

    # Trotz explizit gesetztem mwst_satz muss der Kleinunternehmer-Status
    # serverseitig gewinnen -- sonst koennte versehentlich eine besteuerte
    # Rechnung entstehen (§14c UStG-Risiko).
    resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "betrag_netto": "100", "mwst_satz": "19.00"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["mwst_satz"] == "0.00"
    assert body["betrag_brutto"] == "100.00"

    pdf_resp = await client.get(f"/api/rechnungen/{body['id']}/pdf", headers=auth_headers(token))
    assert pdf_resp.status_code == 200
    assert pdf_resp.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_techniker_cannot_create_rechnung(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/rechnungen", headers=auth_headers(token), json={"kunde_id": str(kunde.id), "betrag_netto": "1"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_bezahlt_setzt_vorgang_auf_abgerechnet(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, status="abgeschlossen")
    token = await login(client, admin.email, "pw-123456")

    created = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "vorgang_id": str(vorgang.id), "betrag_netto": "300.00"},
    )
    rechnung_id = created.json()["id"]

    await client.patch(f"/api/rechnungen/{rechnung_id}", headers=auth_headers(token), json={"status": "versendet"})
    resp = await client.patch(
        f"/api/rechnungen/{rechnung_id}", headers=auth_headers(token), json={"status": "bezahlt"}
    )
    assert resp.status_code == 200
    assert resp.json()["bezahlt_am"] is not None

    async with system_session() as session:
        refreshed = await session.get(Vorgang, vorgang.id)
        assert refreshed.status == "abgerechnet"

    events_resp = await client.get(f"/api/vorgaenge/{vorgang.id}/events", headers=auth_headers(token))
    event_types = [e["event_type"] for e in events_resp.json()]
    assert "rechnung_status" in event_types


@pytest.mark.asyncio
async def test_invalid_transition_entwurf_to_bezahlt_rejected(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    created = await client.post(
        "/api/rechnungen", headers=auth_headers(token), json={"kunde_id": str(kunde.id), "betrag_netto": "10"}
    )
    rechnung_id = created.json()["id"]

    resp = await client.patch(
        f"/api/rechnungen/{rechnung_id}", headers=auth_headers(token), json={"status": "bezahlt"}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_rechnung_pdf_returns_pdf_bytes(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    created = await client.post(
        "/api/rechnungen", headers=auth_headers(token), json={"kunde_id": str(kunde.id), "betrag_netto": "10"}
    )
    rechnung_id = created.json()["id"]

    resp = await client.get(f"/api/rechnungen/{rechnung_id}/pdf", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_mandant_isolation_for_rechnungen(client, make_mandant, make_user, make_kunde):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    admin1 = await make_user(mandant=mandant1, role="mandant_admin", password="pw-123456")
    admin2 = await make_user(mandant=mandant2, role="mandant_admin", password="pw-123456")
    kunde1 = await make_kunde(mandant=mandant1)
    token1 = await login(client, admin1.email, "pw-123456")
    token2 = await login(client, admin2.email, "pw-123456")

    created = await client.post(
        "/api/rechnungen", headers=auth_headers(token1), json={"kunde_id": str(kunde1.id), "betrag_netto": "1"}
    )
    assert created.status_code == 201

    list_resp = await client.get("/api/rechnungen", headers=auth_headers(token2))
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_rechnung_mit_positionen_summe_ueberschreibt_betrag_netto(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "betrag_netto": "999.00",  # wird von den Positionen ueberschrieben
            "positionen": [
                {"beschreibung": "Teilrechnung 1", "menge": "1", "einzelpreis": "100.00"},
                {"beschreibung": "Teilrechnung 2", "menge": "2", "einzelpreis": "50.00"},
            ],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["positionen"]) == 2
    assert body["betrag_netto"] == "200.00"
    assert body["betrag_brutto"] == "238.00"


@pytest.mark.asyncio
async def test_add_position_to_existing_rechnung(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    created = await client.post(
        "/api/rechnungen", headers=auth_headers(token), json={"kunde_id": str(kunde.id)}
    )
    rechnung_id = created.json()["id"]

    resp = await client.post(
        f"/api/rechnungen/{rechnung_id}/positionen",
        headers=auth_headers(token),
        json={"beschreibung": "Material", "menge": "3", "einzelpreis": "20.00"},
    )
    assert resp.status_code == 200
    assert resp.json()["betrag_netto"] == "60.00"

    # Nach Versand koennen keine Positionen mehr ergaenzt werden
    await client.patch(f"/api/rechnungen/{rechnung_id}", headers=auth_headers(token), json={"status": "versendet"})
    versendet_resp = await client.post(
        f"/api/rechnungen/{rechnung_id}/positionen",
        headers=auth_headers(token),
        json={"beschreibung": "Zu spaet", "einzelpreis": "1"},
    )
    assert versendet_resp.status_code == 400


@pytest.mark.asyncio
async def test_betrag_netto_kann_nicht_direkt_geaendert_werden_wenn_positionen_existieren(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    created = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "positionen": [{"beschreibung": "x", "einzelpreis": "10"}]},
    )
    rechnung_id = created.json()["id"]

    resp = await client.patch(
        f"/api/rechnungen/{rechnung_id}", headers=auth_headers(token), json={"betrag_netto": "500.00"}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_rechnung_pdf_mit_positionen(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    created = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "positionen": [{"beschreibung": "Arbeit", "einzelpreis": "42.00"}]},
    )
    rechnung_id = created.json()["id"]

    resp = await client.get(f"/api/rechnungen/{rechnung_id}/pdf", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")
