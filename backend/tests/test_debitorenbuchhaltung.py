"""Tests fuer Zahlungseingaenge auf Ausgangsrechnungen: Teilzahlungen,
offener Betrag, rueckdatierbares Zahlungsdatum, Zahlungs-Storno und der
GoBD-Vertrag (Zahlungen duerfen das archivierte PDF nicht veraendern)."""
import pytest

from app.db.session import system_session
from app.models.vorgang import Vorgang
from tests.conftest import auth_headers, login


async def _rechnung_versendet(client, token, kunde_id, *, netto="1000.00", vorgang_id=None):
    payload = {"kunde_id": str(kunde_id), "betrag_netto": netto}
    if vorgang_id:
        payload["vorgang_id"] = str(vorgang_id)
    erstellt = await client.post("/api/rechnungen", headers=auth_headers(token), json=payload)
    assert erstellt.status_code == 201
    rechnung_id = erstellt.json()["id"]
    versendet = await client.patch(
        f"/api/rechnungen/{rechnung_id}", headers=auth_headers(token), json={"status": "versendet"}
    )
    assert versendet.status_code == 200
    return rechnung_id


@pytest.mark.asyncio
async def test_teilzahlung_setzt_status_teilweise_bezahlt_und_offenen_betrag(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")
    rechnung_id = await _rechnung_versendet(client, token, kunde.id, netto="1000.00")

    resp = await client.post(
        f"/api/rechnungen/{rechnung_id}/zahlungen",
        headers=auth_headers(token),
        json={"betrag": "500.00"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "teilweise_bezahlt"
    assert body["bezahlter_betrag"] == "500.00"
    assert body["offener_betrag"] == "690.00"
    assert body["bezahlt_am"] is None


@pytest.mark.asyncio
async def test_vollzahlung_setzt_status_bezahlt_und_bezahlt_am_auf_zahlungsdatum(
    client, make_mandant, make_user, make_kunde
):
    """Rueckdatiert -- bezahlt_am muss das Datum der Zahlung sein, nicht
    'jetzt'. Das war der eigentliche Kernpunkt von Phase 2."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")
    rechnung_id = await _rechnung_versendet(client, token, kunde.id, netto="100.00")

    resp = await client.post(
        f"/api/rechnungen/{rechnung_id}/zahlungen",
        headers=auth_headers(token),
        json={"betrag": "119.00", "datum": "2026-01-15"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "bezahlt"
    assert body["offener_betrag"] == "0.00"
    assert body["bezahlt_am"].startswith("2026-01-15")


@pytest.mark.asyncio
async def test_zahlung_uebersteigt_offenen_betrag_wird_abgelehnt(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")
    rechnung_id = await _rechnung_versendet(client, token, kunde.id, netto="100.00")

    resp = await client.post(
        f"/api/rechnungen/{rechnung_id}/zahlungen",
        headers=auth_headers(token),
        json={"betrag": "500.00"},
    )
    assert resp.status_code == 400
    assert "119.00" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_zahlung_im_entwurf_abgelehnt(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    erstellt = await client.post(
        "/api/rechnungen", headers=auth_headers(token), json={"kunde_id": str(kunde.id), "betrag_netto": "50"}
    )
    rechnung_id = erstellt.json()["id"]

    resp = await client.post(
        f"/api/rechnungen/{rechnung_id}/zahlungen", headers=auth_headers(token), json={"betrag": "10"}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_zahlungsdatum_in_zukunft_abgelehnt(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")
    rechnung_id = await _rechnung_versendet(client, token, kunde.id, netto="100.00")

    resp = await client.post(
        f"/api/rechnungen/{rechnung_id}/zahlungen",
        headers=auth_headers(token),
        json={"betrag": "10", "datum": "2099-01-01"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_teilzahlung_setzt_vorgang_nicht_auf_abgerechnet(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    """Nur eine VOLLE Zahlung darf den Vorgang auf 'abgerechnet' setzen --
    der Nebeneffekt darf bei teilweise_bezahlt nicht feuern."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")
    rechnung_id = await _rechnung_versendet(client, token, kunde.id, netto="1000.00", vorgang_id=vorgang.id)

    await client.post(
        f"/api/rechnungen/{rechnung_id}/zahlungen", headers=auth_headers(token), json={"betrag": "500.00"}
    )

    async with system_session() as session:
        aktuell = await session.get(Vorgang, vorgang.id)
        assert aktuell.status != "abgerechnet"

    await client.post(
        f"/api/rechnungen/{rechnung_id}/zahlungen", headers=auth_headers(token), json={"betrag": "690.00"}
    )
    async with system_session() as session:
        aktuell = await session.get(Vorgang, vorgang.id)
        assert aktuell.status == "abgerechnet"


@pytest.mark.asyncio
async def test_zahlung_aendert_archiviertes_pdf_nicht(client, make_mandant, make_user, make_kunde):
    """Der GoBD-Vertrag: Zahlungen sind Bewegungsdaten, kein Belegtinhalt --
    das PDF muss vor und nach einer Zahlungsbuchung byte-identisch sein."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")
    rechnung_id = await _rechnung_versendet(client, token, kunde.id, netto="300.00")

    pdf_vor = await client.get(f"/api/rechnungen/{rechnung_id}/pdf", headers=auth_headers(token))
    assert pdf_vor.status_code == 200

    zahlung = await client.post(
        f"/api/rechnungen/{rechnung_id}/zahlungen", headers=auth_headers(token), json={"betrag": "100.00"}
    )
    assert zahlung.status_code == 201

    pdf_nach = await client.get(f"/api/rechnungen/{rechnung_id}/pdf", headers=auth_headers(token))
    assert pdf_nach.status_code == 200
    assert pdf_vor.content == pdf_nach.content


@pytest.mark.asyncio
async def test_zahlung_storno_bucht_gegenposition_und_senkt_status(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")
    rechnung_id = await _rechnung_versendet(client, token, kunde.id, netto="200.00")

    zahlung = await client.post(
        f"/api/rechnungen/{rechnung_id}/zahlungen", headers=auth_headers(token), json={"betrag": "238.00"}
    )
    assert zahlung.json()["status"] == "bezahlt"
    zahlung_id = zahlung.json()["zahlungen"][-1]["id"]

    storno = await client.post(
        f"/api/rechnungen/{rechnung_id}/zahlungen/{zahlung_id}/storno", headers=auth_headers(token)
    )
    assert storno.status_code == 201
    body = storno.json()
    assert body["status"] == "versendet"
    assert body["bezahlt_am"] is None
    assert body["offener_betrag"] == "238.00"
    assert len(body["zahlungen"]) == 2
    assert body["zahlungen"][-1]["betrag"] == "-238.00"
    assert body["zahlungen"][-1]["storniert_zahlung_id"] == zahlung_id


@pytest.mark.asyncio
async def test_zahlung_storno_zweimal_abgelehnt(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")
    rechnung_id = await _rechnung_versendet(client, token, kunde.id, netto="100.00")

    zahlung = await client.post(
        f"/api/rechnungen/{rechnung_id}/zahlungen", headers=auth_headers(token), json={"betrag": "50.00"}
    )
    zahlung_id = zahlung.json()["zahlungen"][-1]["id"]

    erstes_storno = await client.post(
        f"/api/rechnungen/{rechnung_id}/zahlungen/{zahlung_id}/storno", headers=auth_headers(token)
    )
    assert erstes_storno.status_code == 201

    zweites_storno = await client.post(
        f"/api/rechnungen/{rechnung_id}/zahlungen/{zahlung_id}/storno", headers=auth_headers(token)
    )
    assert zweites_storno.status_code == 400


@pytest.mark.asyncio
async def test_patch_bezahlt_bucht_restbetrag_als_zahlung(client, make_mandant, make_user, make_kunde):
    """Sichert die Invariante offener_betrag == brutto - Summe(Zahlungen):
    'als bezahlt markieren' ohne Zahlungen muss selbst eine Zahlung ueber
    den vollen Betrag anlegen, sonst reproduziert man das Altdatenproblem,
    das der Backfill in Migration 0056 behoben hat."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")
    rechnung_id = await _rechnung_versendet(client, token, kunde.id, netto="500.00")

    resp = await client.patch(
        f"/api/rechnungen/{rechnung_id}", headers=auth_headers(token), json={"status": "bezahlt"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "bezahlt"
    assert body["offener_betrag"] == "0.00"
    assert body["bezahlter_betrag"] == "595.00"
    assert len(body["zahlungen"]) == 1
    assert body["zahlungen"][0]["notiz"] == "Restbetrag beim manuellen Abschluss gebucht"


@pytest.mark.asyncio
async def test_storno_auch_bei_teilweise_bezahlt_moeglich(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")
    rechnung_id = await _rechnung_versendet(client, token, kunde.id, netto="1000.00")

    teilzahlung = await client.post(
        f"/api/rechnungen/{rechnung_id}/zahlungen", headers=auth_headers(token), json={"betrag": "500.00"}
    )
    assert teilzahlung.json()["status"] == "teilweise_bezahlt"

    storno = await client.post(f"/api/rechnungen/{rechnung_id}/storno", headers=auth_headers(token))
    assert storno.status_code == 201
    assert storno.json()["ist_storno"] is True


@pytest.mark.asyncio
async def test_rechnung_ohne_zahlungen_hat_offenen_betrag_gleich_brutto(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")
    rechnung_id = await _rechnung_versendet(client, token, kunde.id, netto="42.00")

    resp = await client.get(f"/api/rechnungen/{rechnung_id}", headers=auth_headers(token))
    body = resp.json()
    assert body["offener_betrag"] == body["betrag_brutto"] == "49.98"
    assert body["bezahlter_betrag"] == "0.00"


@pytest.mark.asyncio
async def test_faellig_am_nach_versand_nicht_mehr_aenderbar(client, make_mandant, make_user, make_kunde):
    """GoBD-Luecke aus Phase 2 geschlossen: faellig_am/leistungsdatum stehen
    im archivierten PDF und duerfen nach dem Versand nicht mehr geaendert
    werden."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")
    rechnung_id = await _rechnung_versendet(client, token, kunde.id, netto="10.00")

    resp = await client.patch(
        f"/api/rechnungen/{rechnung_id}", headers=auth_headers(token), json={"faellig_am": "2026-12-31"}
    )
    assert resp.status_code == 400
