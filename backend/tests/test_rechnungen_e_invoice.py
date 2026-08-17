import pytest

from tests.conftest import auth_headers, login

_FIRMENDATEN_VOLLSTAENDIG = {
    "e_rechnung_aktiv": True,
    "adresse": {"strasse": "Musterstr. 1", "plz": "12345", "ort": "Musterstadt"},
    "ust_idnr": "DE123456789",
}


async def _aktiviere_e_rechnung(client, token, firmendaten: dict = _FIRMENDATEN_VOLLSTAENDIG) -> None:
    resp = await client.patch(
        "/api/mandant/einstellungen", headers=auth_headers(token), json={"firmendaten": firmendaten}
    )
    assert resp.status_code == 200


async def _rechnung_versendet(client, token, kunde_id: str, **kwargs) -> dict:
    create_resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={
            "kunde_id": kunde_id,
            "betrag_netto": "300.00",
            "mwst_satz": "19.00",
            "leistungsdatum": "2026-08-10",
            **kwargs,
        },
    )
    assert create_resp.status_code == 201
    rechnung_id = create_resp.json()["id"]
    versand_resp = await client.patch(
        f"/api/rechnungen/{rechnung_id}", headers=auth_headers(token), json={"status": "versendet"}
    )
    assert versand_resp.status_code == 200
    return versand_resp.json()


@pytest.mark.asyncio
async def test_versand_erzeugt_hybrid_pdf_und_xml_wenn_vollstaendig(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(
        mandant=mandant,
        typ="gewerbe",
        adresse={"strasse": "Kundenweg 2", "plz": "54321", "ort": "Kundenstadt"},
        ust_idnr="DE987654321",
    )
    token = await login(client, admin.email, "pw-123456")
    await _aktiviere_e_rechnung(client, token)

    rechnung = await _rechnung_versendet(client, token, str(kunde.id))
    assert rechnung["xml_object_key"] is not None

    xml_resp = await client.get(f"/api/rechnungen/{rechnung['id']}/xml", headers=auth_headers(token))
    assert xml_resp.status_code == 200
    assert xml_resp.headers["content-type"].startswith("application/xml")
    assert xml_resp.content.startswith(b"<?xml")
    assert rechnung["rechnungsnummer"].encode() in xml_resp.content

    pdf_resp = await client.get(f"/api/rechnungen/{rechnung['id']}/pdf", headers=auth_headers(token))
    assert pdf_resp.status_code == 200
    assert pdf_resp.content.startswith(b"%PDF")
    assert b"factur-x.xml" in pdf_resp.content


@pytest.mark.asyncio
async def test_versand_faellt_still_auf_normales_pdf_zurueck_wenn_kunde_unvollstaendig(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(
        mandant=mandant,
        typ="gewerbe",
        adresse={"strasse": "Kundenweg 2", "plz": "54321", "ort": "Kundenstadt"},
    )
    token = await login(client, admin.email, "pw-123456")
    await _aktiviere_e_rechnung(client, token)

    rechnung = await _rechnung_versendet(client, token, str(kunde.id))
    assert rechnung["xml_object_key"] is None

    xml_resp = await client.get(f"/api/rechnungen/{rechnung['id']}/xml", headers=auth_headers(token))
    assert xml_resp.status_code == 404

    pdf_resp = await client.get(f"/api/rechnungen/{rechnung['id']}/pdf", headers=auth_headers(token))
    assert pdf_resp.status_code == 200
    assert pdf_resp.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_versand_ohne_e_rechnung_toggle_erzeugt_kein_xml(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(
        mandant=mandant,
        typ="gewerbe",
        adresse={"strasse": "Kundenweg 2", "plz": "54321", "ort": "Kundenstadt"},
        ust_idnr="DE987654321",
    )
    token = await login(client, admin.email, "pw-123456")
    await _aktiviere_e_rechnung(
        client, token, {"adresse": _FIRMENDATEN_VOLLSTAENDIG["adresse"], "ust_idnr": _FIRMENDATEN_VOLLSTAENDIG["ust_idnr"]}
    )

    rechnung = await _rechnung_versendet(client, token, str(kunde.id))
    assert rechnung["xml_object_key"] is None


@pytest.mark.asyncio
async def test_privater_kunde_ohne_ust_idnr_bekommt_trotzdem_e_rechnung(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(
        mandant=mandant,
        typ="privat",
        adresse={"strasse": "Kundenweg 2", "plz": "54321", "ort": "Kundenstadt"},
    )
    token = await login(client, admin.email, "pw-123456")
    await _aktiviere_e_rechnung(client, token)

    rechnung = await _rechnung_versendet(client, token, str(kunde.id))
    assert rechnung["xml_object_key"] is not None


@pytest.mark.asyncio
async def test_hybrid_pdf_und_xml_aendern_sich_nicht_nach_firmendaten_aenderung(
    client, make_mandant, make_user, make_kunde
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(
        mandant=mandant,
        typ="gewerbe",
        adresse={"strasse": "Kundenweg 2", "plz": "54321", "ort": "Kundenstadt"},
        ust_idnr="DE987654321",
    )
    token = await login(client, admin.email, "pw-123456")
    await _aktiviere_e_rechnung(client, token)

    rechnung = await _rechnung_versendet(client, token, str(kunde.id))
    pdf_vor = await client.get(f"/api/rechnungen/{rechnung['id']}/pdf", headers=auth_headers(token))
    xml_vor = await client.get(f"/api/rechnungen/{rechnung['id']}/xml", headers=auth_headers(token))

    await client.patch(
        "/api/mandant/einstellungen",
        headers=auth_headers(token),
        json={"firmendaten": {**_FIRMENDATEN_VOLLSTAENDIG, "adresse": {"strasse": "Andere Str. 9", "plz": "99999", "ort": "Woanders"}}},
    )

    pdf_nach = await client.get(f"/api/rechnungen/{rechnung['id']}/pdf", headers=auth_headers(token))
    xml_nach = await client.get(f"/api/rechnungen/{rechnung['id']}/xml", headers=auth_headers(token))

    assert pdf_vor.content == pdf_nach.content
    assert xml_vor.content == xml_nach.content


@pytest.mark.asyncio
async def test_kunde_ust_idnr_wird_ueber_api_gespeichert(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    create_resp = await client.post(
        "/api/kunden",
        headers=auth_headers(token),
        json={"name": "Neuer Kunde", "typ": "gewerbe", "ust_idnr": "DE111222333"},
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["ust_idnr"] == "DE111222333"

    kunde_id = create_resp.json()["id"]
    update_resp = await client.patch(
        f"/api/kunden/{kunde_id}", headers=auth_headers(token), json={"ust_idnr": "DE444555666"}
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["ust_idnr"] == "DE444555666"
