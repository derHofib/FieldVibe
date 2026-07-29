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
