import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_ust_va_bericht_aggregiert_ausgang_und_eingang(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    rechnung_resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "betrag_netto": "1000.00", "mwst_satz": "19.00"},
    )
    rechnung_id = rechnung_resp.json()["id"]
    await client.patch(
        f"/api/rechnungen/{rechnung_id}", headers=auth_headers(token), json={"status": "versendet"}
    )

    await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={
            "lieferant_name": "Sonepar",
            "rechnungsnummer_lieferant": "RE-1",
            "rechnungsdatum": "2026-08-01",
            "betrag_netto": "200.00",
            "mwst_satz": "19.00",
        },
    )

    resp = await client.get(
        "/api/auswertung/ust-va?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    body = resp.json()

    umsatz19 = next(z for z in body["umsatzsteuer_saetze"] if z["satz"] == "19.00")
    assert umsatz19["netto"] == "1000.00"
    assert umsatz19["steuer"] == "190.00"

    vorsteuer19 = next(z for z in body["vorsteuer_saetze"] if z["satz"] == "19.00")
    assert vorsteuer19["netto"] == "200.00"
    assert vorsteuer19["steuer"] == "38.00"

    assert body["summe_umsatzsteuer"] == "190.00"
    assert body["summe_vorsteuer"] == "38.00"
    assert body["zahllast"] == "152.00"


@pytest.mark.asyncio
async def test_entwurf_rechnung_zaehlt_nicht(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "betrag_netto": "1000.00", "mwst_satz": "19.00"},
    )

    resp = await client.get(
        "/api/auswertung/ust-va?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    assert resp.json()["umsatzsteuer_saetze"] == []
    assert resp.json()["summe_umsatzsteuer"] == "0.00"


@pytest.mark.asyncio
async def test_stornierte_eingangsrechnung_zaehlt_nicht_als_vorsteuer(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={
            "lieferant_name": "Sonepar",
            "rechnungsnummer_lieferant": "RE-2",
            "rechnungsdatum": "2026-08-01",
            "betrag_netto": "200.00",
            "mwst_satz": "19.00",
        },
    )
    await client.patch(
        f"/api/eingangsrechnungen/{resp.json()['id']}",
        headers=auth_headers(token),
        json={"status": "storniert"},
    )

    bericht = await client.get(
        "/api/auswertung/ust-va?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token)
    )
    assert bericht.json()["vorsteuer_saetze"] == []


@pytest.mark.asyncio
async def test_mandant_isolation(client, make_mandant, make_user, make_kunde):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    admin1 = await make_user(mandant=mandant1, role="mandant_admin", password="pw-123456")
    admin2 = await make_user(mandant=mandant2, role="mandant_admin", password="pw-123456")
    kunde1 = await make_kunde(mandant=mandant1)
    token1 = await login(client, admin1.email, "pw-123456")
    token2 = await login(client, admin2.email, "pw-123456")

    rechnung_resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token1),
        json={"kunde_id": str(kunde1.id), "betrag_netto": "1000.00", "mwst_satz": "19.00"},
    )
    await client.patch(
        f"/api/rechnungen/{rechnung_resp.json()['id']}",
        headers=auth_headers(token1),
        json={"status": "versendet"},
    )

    resp2 = await client.get(
        "/api/auswertung/ust-va?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token2)
    )
    assert resp2.json()["summe_umsatzsteuer"] == "0.00"


@pytest.mark.asyncio
async def test_bis_vor_von_wird_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get(
        "/api/auswertung/ust-va?von=2026-08-10&bis=2026-08-01", headers=auth_headers(token)
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_datev_export_liefert_csv(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    rechnung_resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "betrag_netto": "1000.00", "mwst_satz": "19.00"},
    )
    rechnungsnummer = rechnung_resp.json()["rechnungsnummer"]
    await client.patch(
        f"/api/rechnungen/{rechnung_resp.json()['id']}",
        headers=auth_headers(token),
        json={"status": "versendet"},
    )

    resp = await client.get(
        "/api/auswertung/datev-export?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    text = resp.content.decode("utf-8")
    assert text.startswith("EXTF")
    assert rechnungsnummer in text
    assert "1190,00" in text  # Brutto (1000 + 19% USt), Komma statt Punkt


@pytest.mark.asyncio
async def test_offene_posten_kombiniert_debitoren_und_kreditoren(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, name="Café Sonnenschein")
    token = await login(client, admin.email, "pw-123456")

    rechnung_resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "betrag_netto": "1000.00", "mwst_satz": "19.00", "faellig_am": "2020-01-01"},
    )
    rechnung_id = rechnung_resp.json()["id"]
    await client.patch(f"/api/rechnungen/{rechnung_id}", headers=auth_headers(token), json={"status": "versendet"})
    await client.post(
        f"/api/rechnungen/{rechnung_id}/zahlungen", headers=auth_headers(token), json={"betrag": "500.00"}
    )

    eingang_resp = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={
            "lieferant_name": "Sonepar",
            "rechnungsnummer_lieferant": "RE-OP-1",
            "rechnungsdatum": "2020-01-01",
            "faellig_am": "2020-01-15",
            "betrag_netto": "300.00",
            "mwst_satz": "19.00",
        },
    )
    eingang_id = eingang_resp.json()["id"]

    resp = await client.get("/api/auswertung/offene-posten", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()

    debitor = next(d for d in body["debitoren"] if d["id"] == rechnung_id)
    assert debitor["offener_betrag"] == "690.00"  # 1190 brutto - 500 gezahlt
    assert debitor["tage_ueberfaellig"] > 1000

    kreditor = next(k for k in body["kreditoren"] if k["id"] == eingang_id)
    assert kreditor["offener_betrag"] == "357.00"  # 300 + 19%
    assert kreditor["nummer"] == "RE-OP-1"

    assert body["summe_debitoren"] == "690.00"
    assert body["summe_kreditoren"] == "357.00"

    bucket_labels_debitoren = {b["label"] for b in body["debitoren_buckets"]}
    assert bucket_labels_debitoren == {"90+ Tage"}


@pytest.mark.asyncio
async def test_offene_posten_ohne_faelligkeitsdatum_zaehlt_als_nicht_faellig(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    rechnung_resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "betrag_netto": "100.00", "mwst_satz": "19.00"},
    )
    rechnung_id = rechnung_resp.json()["id"]
    await client.patch(f"/api/rechnungen/{rechnung_id}", headers=auth_headers(token), json={"status": "versendet"})

    resp = await client.get("/api/auswertung/offene-posten", headers=auth_headers(token))
    debitor = next(d for d in resp.json()["debitoren"] if d["id"] == rechnung_id)
    assert debitor["faellig_am"] is None
    assert debitor["tage_ueberfaellig"] == 0
    assert {b["label"] for b in resp.json()["debitoren_buckets"]} == {"Nicht fällig"}


@pytest.mark.asyncio
async def test_offene_posten_vollstaendig_bezahlte_rechnung_fehlt(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    rechnung_resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "betrag_netto": "100.00", "mwst_satz": "19.00"},
    )
    rechnung_id = rechnung_resp.json()["id"]
    await client.patch(f"/api/rechnungen/{rechnung_id}", headers=auth_headers(token), json={"status": "versendet"})
    await client.patch(f"/api/rechnungen/{rechnung_id}", headers=auth_headers(token), json={"status": "bezahlt"})

    resp = await client.get("/api/auswertung/offene-posten", headers=auth_headers(token))
    assert all(d["id"] != rechnung_id for d in resp.json()["debitoren"])


@pytest.mark.asyncio
async def test_offene_posten_mandant_isolation(client, make_mandant, make_user, make_kunde):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    admin1 = await make_user(mandant=mandant1, role="mandant_admin", password="pw-123456")
    admin2 = await make_user(mandant=mandant2, role="mandant_admin", password="pw-123456")
    kunde1 = await make_kunde(mandant=mandant1)
    token1 = await login(client, admin1.email, "pw-123456")
    token2 = await login(client, admin2.email, "pw-123456")

    rechnung_resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token1),
        json={"kunde_id": str(kunde1.id), "betrag_netto": "100.00", "mwst_satz": "19.00"},
    )
    await client.patch(
        f"/api/rechnungen/{rechnung_resp.json()['id']}", headers=auth_headers(token1), json={"status": "versendet"}
    )

    resp2 = await client.get("/api/auswertung/offene-posten", headers=auth_headers(token2))
    assert resp2.json()["debitoren"] == []
    assert resp2.json()["summe_debitoren"] == "0.00"


@pytest.mark.asyncio
async def test_ust_va_unveraendert_durch_zahlungen(client, make_mandant, make_user, make_kunde):
    """UStVA/DATEV-Export sind Soll-Versteuerung (versendet_am) -- eine
    Teilzahlung auf eine versendete Rechnung darf die bereits ausgewiesene
    Umsatzsteuer nicht veraendern."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")

    rechnung_resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={"kunde_id": str(kunde.id), "betrag_netto": "1000.00", "mwst_satz": "19.00"},
    )
    rechnung_id = rechnung_resp.json()["id"]
    await client.patch(f"/api/rechnungen/{rechnung_id}", headers=auth_headers(token), json={"status": "versendet"})

    vor = await client.get(
        "/api/auswertung/ust-va?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token)
    )

    await client.post(
        f"/api/rechnungen/{rechnung_id}/zahlungen", headers=auth_headers(token), json={"betrag": "500.00"}
    )

    nach = await client.get(
        "/api/auswertung/ust-va?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token)
    )
    assert vor.json() == nach.json()


@pytest.mark.asyncio
async def test_mitarbeiter_ohne_abrechnung_recht_cannot_access_auswertung(
    client, make_mandant, make_user
):
    mandant = await make_mandant()
    # "mitarbeiter" hat laut _LEGACY_RECHTE keine abrechnung-Rechte (nicht
    # einmal "sehen") -- anders als "techniker", der dort "sehen" besitzt.
    mitarbeiter = await make_user(mandant=mandant, role="mitarbeiter", password="pw-123456")
    token = await login(client, mitarbeiter.email, "pw-123456")

    resp = await client.get(
        "/api/auswertung/ust-va?von=2020-01-01&bis=2030-12-31", headers=auth_headers(token)
    )
    assert resp.status_code == 403
