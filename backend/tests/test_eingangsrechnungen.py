import io

import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_create_eingangsrechnung_mit_lieferant(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    lieferant_resp = await client.post(
        "/api/lieferanten", headers=auth_headers(token), json={"name": "Sonepar"}
    )
    lieferant_id = lieferant_resp.json()["id"]

    resp = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={
            "lieferant_id": lieferant_id,
            "rechnungsnummer_lieferant": "RE-2026-4711",
            "rechnungsdatum": "2026-08-01",
            "betrag_netto": "100.00",
            "kategorie": "wareneinkauf",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["lieferant_name"] == "Sonepar"
    assert body["status"] == "offen"
    assert body["betrag_brutto"] == "119.00"


@pytest.mark.asyncio
async def test_create_eingangsrechnung_ohne_lieferant_braucht_namen(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    ohne_namen = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={"rechnungsnummer_lieferant": "RE-1", "rechnungsdatum": "2026-08-01"},
    )
    assert ohne_namen.status_code == 400

    mit_namen = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={
            "lieferant_name": "Vermieter GmbH",
            "rechnungsnummer_lieferant": "RE-2",
            "rechnungsdatum": "2026-08-01",
            "betrag_netto": "500.00",
            "kategorie": "miete",
        },
    )
    assert mit_namen.status_code == 201
    assert mit_namen.json()["lieferant_name"] == "Vermieter GmbH"


@pytest.mark.asyncio
async def test_positionen_bestimmen_die_summe(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={
            "lieferant_name": "Sonepar",
            "rechnungsnummer_lieferant": "RE-42",
            "rechnungsdatum": "2026-08-01",
            "betrag_netto": "999.00",
            "positionen": [
                {"beschreibung": "Kabel", "menge": "10", "einheit": "m", "einzelpreis": "2.50"},
                {"beschreibung": "Dose", "menge": "5", "einheit": "Stk", "einzelpreis": "1.00"},
            ],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["betrag_netto"] == "30.00"
    assert len(body["positionen"]) == 2

    add_resp = await client.post(
        f"/api/eingangsrechnungen/{body['id']}/positionen",
        headers=auth_headers(token),
        json={"beschreibung": "Klemme", "menge": "20", "einheit": "Stk", "einzelpreis": "0.50"},
    )
    assert add_resp.status_code == 200
    assert add_resp.json()["betrag_netto"] == "40.00"


@pytest.mark.asyncio
async def test_status_uebergaenge(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={
            "lieferant_name": "Sonepar",
            "rechnungsnummer_lieferant": "RE-99",
            "rechnungsdatum": "2026-08-01",
            "betrag_netto": "50.00",
        },
    )
    eingangsrechnung_id = resp.json()["id"]

    ungueltig = await client.patch(
        f"/api/eingangsrechnungen/{eingangsrechnung_id}",
        headers=auth_headers(token),
        json={"status": "offen"},
    )
    assert ungueltig.status_code == 400

    bezahlt = await client.patch(
        f"/api/eingangsrechnungen/{eingangsrechnung_id}",
        headers=auth_headers(token),
        json={"status": "bezahlt"},
    )
    assert bezahlt.status_code == 200
    assert bezahlt.json()["status"] == "bezahlt"
    assert bezahlt.json()["bezahlt_am"] is not None

    weiterer_wechsel = await client.patch(
        f"/api/eingangsrechnungen/{eingangsrechnung_id}",
        headers=auth_headers(token),
        json={"status": "storniert"},
    )
    assert weiterer_wechsel.status_code == 400


@pytest.mark.asyncio
async def test_delete_nur_im_status_offen(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={
            "lieferant_name": "Sonepar",
            "rechnungsnummer_lieferant": "RE-100",
            "rechnungsdatum": "2026-08-01",
            "betrag_netto": "50.00",
        },
    )
    eingangsrechnung_id = resp.json()["id"]
    await client.patch(
        f"/api/eingangsrechnungen/{eingangsrechnung_id}",
        headers=auth_headers(token),
        json={"status": "bezahlt"},
    )

    verboten = await client.delete(
        f"/api/eingangsrechnungen/{eingangsrechnung_id}", headers=auth_headers(token)
    )
    assert verboten.status_code == 409

    resp2 = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={
            "lieferant_name": "Sonepar",
            "rechnungsnummer_lieferant": "RE-101",
            "rechnungsdatum": "2026-08-01",
            "betrag_netto": "50.00",
        },
    )
    erlaubt = await client.delete(
        f"/api/eingangsrechnungen/{resp2.json()['id']}", headers=auth_headers(token)
    )
    assert erlaubt.status_code == 204


@pytest.mark.asyncio
async def test_beleg_upload_und_download_url(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={
            "lieferant_name": "Sonepar",
            "rechnungsnummer_lieferant": "RE-200",
            "rechnungsdatum": "2026-08-01",
            "betrag_netto": "50.00",
        },
    )
    eingangsrechnung_id = resp.json()["id"]
    assert resp.json()["beleg_object_key"] is None

    upload = await client.post(
        f"/api/eingangsrechnungen/{eingangsrechnung_id}/beleg",
        headers=auth_headers(token),
        files={"file": ("beleg.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
    )
    assert upload.status_code == 200
    assert upload.json()["beleg_object_key"] is not None

    url_resp = await client.get(
        f"/api/eingangsrechnungen/{eingangsrechnung_id}/beleg-url", headers=auth_headers(token)
    )
    assert url_resp.status_code == 200
    assert url_resp.json()["url"] is not None

    remove_resp = await client.delete(
        f"/api/eingangsrechnungen/{eingangsrechnung_id}/beleg", headers=auth_headers(token)
    )
    assert remove_resp.status_code == 200
    assert remove_resp.json()["beleg_object_key"] is None


@pytest.mark.asyncio
async def test_mandant_isolation(client, make_mandant, make_user):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    admin1 = await make_user(mandant=mandant1, role="mandant_admin", password="pw-123456")
    admin2 = await make_user(mandant=mandant2, role="mandant_admin", password="pw-123456")
    token1 = await login(client, admin1.email, "pw-123456")
    token2 = await login(client, admin2.email, "pw-123456")

    await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token1),
        json={
            "lieferant_name": "Nur Betrieb1",
            "rechnungsnummer_lieferant": "RE-1",
            "rechnungsdatum": "2026-08-01",
            "betrag_netto": "10.00",
        },
    )

    list_resp = await client.get("/api/eingangsrechnungen", headers=auth_headers(token2))
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_techniker_cannot_create_eingangsrechnung(client, make_mandant, make_user):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={
            "lieferant_name": "Sonepar",
            "rechnungsnummer_lieferant": "RE-1",
            "rechnungsdatum": "2026-08-01",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_skonto_felder_gespeichert_und_berechnet(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={
            "lieferant_name": "Sonepar",
            "rechnungsnummer_lieferant": "RE-300",
            "rechnungsdatum": "2026-08-01",
            "betrag_netto": "100.00",
            "skonto_prozent": "2.00",
            "skonto_tage": 10,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["betrag_brutto"] == "119.00"
    assert body["skonto_frist"] == "2026-08-11"
    assert body["skonto_betrag"] == "2.38"


@pytest.mark.asyncio
async def test_teilzahlung_reduziert_offenen_betrag(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={
            "lieferant_name": "Sonepar",
            "rechnungsnummer_lieferant": "RE-301",
            "rechnungsdatum": "2026-08-01",
            "betrag_netto": "100.00",
        },
    )
    eingangsrechnung_id = resp.json()["id"]

    zahlung = await client.post(
        f"/api/eingangsrechnungen/{eingangsrechnung_id}/zahlungen",
        headers=auth_headers(token),
        json={"betrag": "50.00"},
    )
    assert zahlung.status_code == 201
    body = zahlung.json()
    assert body["status"] == "offen"
    assert body["bezahlter_betrag"] == "50.00"
    assert body["offener_betrag"] == "69.00"
    assert len(body["zahlungen"]) == 1


@pytest.mark.asyncio
async def test_vollzahlung_setzt_status_bezahlt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={
            "lieferant_name": "Sonepar",
            "rechnungsnummer_lieferant": "RE-302",
            "rechnungsdatum": "2026-08-01",
            "betrag_netto": "100.00",
        },
    )
    eingangsrechnung_id = resp.json()["id"]

    zahlung = await client.post(
        f"/api/eingangsrechnungen/{eingangsrechnung_id}/zahlungen",
        headers=auth_headers(token),
        json={"betrag": "119.00"},
    )
    assert zahlung.status_code == 201
    body = zahlung.json()
    assert body["status"] == "bezahlt"
    assert body["bezahlt_am"] is not None
    assert body["offener_betrag"] == "0.00"


@pytest.mark.asyncio
async def test_zahlung_uebersteigt_offenen_betrag_wird_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={
            "lieferant_name": "Sonepar",
            "rechnungsnummer_lieferant": "RE-303",
            "rechnungsdatum": "2026-08-01",
            "betrag_netto": "100.00",
        },
    )
    eingangsrechnung_id = resp.json()["id"]

    zahlung = await client.post(
        f"/api/eingangsrechnungen/{eingangsrechnung_id}/zahlungen",
        headers=auth_headers(token),
        json={"betrag": "200.00"},
    )
    assert zahlung.status_code == 400


@pytest.mark.asyncio
async def test_zahlung_nur_bei_offener_rechnung(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={
            "lieferant_name": "Sonepar",
            "rechnungsnummer_lieferant": "RE-304",
            "rechnungsdatum": "2026-08-01",
            "betrag_netto": "100.00",
        },
    )
    eingangsrechnung_id = resp.json()["id"]
    await client.patch(
        f"/api/eingangsrechnungen/{eingangsrechnung_id}",
        headers=auth_headers(token),
        json={"status": "storniert"},
    )

    zahlung = await client.post(
        f"/api/eingangsrechnungen/{eingangsrechnung_id}/zahlungen",
        headers=auth_headers(token),
        json={"betrag": "10.00"},
    )
    assert zahlung.status_code == 400


@pytest.mark.asyncio
async def test_skonto_kann_nur_bei_offener_rechnung_geaendert_werden(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={
            "lieferant_name": "Sonepar",
            "rechnungsnummer_lieferant": "RE-305",
            "rechnungsdatum": "2026-08-01",
            "betrag_netto": "100.00",
        },
    )
    eingangsrechnung_id = resp.json()["id"]
    await client.patch(
        f"/api/eingangsrechnungen/{eingangsrechnung_id}",
        headers=auth_headers(token),
        json={"status": "storniert"},
    )

    patch_resp = await client.patch(
        f"/api/eingangsrechnungen/{eingangsrechnung_id}",
        headers=auth_headers(token),
        json={"skonto_prozent": "3.00"},
    )
    assert patch_resp.status_code == 400


@pytest.mark.asyncio
async def test_export_csv_enthaelt_offenen_betrag(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/eingangsrechnungen",
        headers=auth_headers(token),
        json={
            "lieferant_name": "Sonepar",
            "rechnungsnummer_lieferant": "RE-400",
            "rechnungsdatum": "2026-08-01",
            "betrag_netto": "100.00",
            "mwst_satz": "19.00",
        },
    )
    rechnungsnummer = resp.json()["rechnungsnummer_lieferant"]

    export = await client.get("/api/eingangsrechnungen/export/csv", headers=auth_headers(token))
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    text = export.content.decode("utf-8-sig")
    assert rechnungsnummer in text
    assert "119.00" in text
    assert "0.00" in text
