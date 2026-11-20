"""Etappe B/C (Migrationen 0126/0127): Ihr Zeichen + Leistungsort an Rechnung/Angebot (Vorbelegung, Snapshot, PDF,
E-Rechnung), abweichender Rechnungsempfaenger (WEG) und "verwaltet von" am Kunden."""
from io import BytesIO

import pymupdf
import pytest
from lxml import etree

from tests.conftest import auth_headers, login
from tests.test_steuer_freischaltung import _E_RECHNUNG, _KUNDE_E_RECHNUNG

PW = "pw-123456"
POS = [{"beschreibung": "Heizungswartung", "menge": "1", "einheit": "psch", "einzelpreis": "100.00"}]
RAM = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"


async def _setup(client, make_mandant, make_user, make_kunde, *, firmendaten=_E_RECHNUNG, **kunde_kw):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW)
    kunde = await make_kunde(mandant=mandant, name="Hausverwaltung Nord", **{**_KUNDE_E_RECHNUNG, **kunde_kw})
    h = auth_headers(await login(client, admin.email, PW))
    resp = await client.patch("/api/mandant/einstellungen", headers=h, json={"firmendaten": firmendaten})
    assert resp.status_code == 200, resp.text
    return mandant, admin, kunde, h


async def _post(client, h, pfad, **body):
    r = await client.post(pfad, headers=h, json=body)
    assert r.status_code in (200, 201), r.text
    return r.json()


async def _standort(client, h, kunde, adresse=None, bezeichnung="Liegenschaft Rosenweg"):
    adresse = adresse or {"strasse": "Rosenweg 5", "plz": "50667", "ort": "Köln"}
    return await _post(client, h, "/api/standorte", kunde_id=str(kunde.id), bezeichnung=bezeichnung, adresse=adresse)


async def _auftrag(client, h, kunde, **kw):
    return await _post(client, h, "/api/auftraege", titel="Heizung", kunde_id=str(kunde.id), **kw)


async def _vorgang(client, h, kunde, **kw):
    return await _post(
        client, h, "/api/vorgaenge", kunde_id=str(kunde.id), titel="Störung", abrechnungsart="aufwand",
        leistungstyp="stoerung", **kw,
    )


async def _rechnung(client, h, kunde, vorgang=None, **kw):
    body = {"kunde_id": str(kunde.id), "mwst_satz": "19.00", "leistungsdatum": "2026-08-10", "positionen": POS, **kw}
    if vorgang is not None:
        body["vorgang_id"] = vorgang["id"]
    return await _post(client, h, "/api/rechnungen", **body)


def _ort(beleg: dict) -> dict | None:
    """Leistungsort ohne leere Felder (die Antwort fuehrt alle fuenf Schluessel)."""
    ort = beleg["leistungsort"]
    return None if ort is None else {k: v for k, v in ort.items() if v is not None}


def _pdf_text(inhalt: bytes) -> str:
    with pymupdf.open(stream=BytesIO(inhalt), filetype="pdf") as dok:
        return "\n".join(seite.get_text() for seite in dok)


@pytest.fixture
async def hv(client, make_mandant, make_user, make_kunde):
    mandant, admin, kunde, h = await _setup(client, make_mandant, make_user, make_kunde)
    standort = await _standort(client, h, kunde)
    auftrag = await _auftrag(
        client, h, kunde, standort_id=standort["id"], einheit="Whg. 3, 2. OG links", kunden_referenz="HV-2026-17"
    )
    vorgang = await _vorgang(client, h, kunde, auftrag_id=auftrag["id"])
    return {"mandant": mandant, "kunde": kunde, "h": h, "standort": standort, "auftrag": auftrag, "vorgang": vorgang}


# --- B1: Vorbelegung -------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rechnung_aus_vorgang_wird_vorbelegt(client, hv):
    r = await _rechnung(client, hv["h"], hv["kunde"], hv["vorgang"])
    assert r["kunden_referenz"] == "HV-2026-17"
    assert _ort(r) == {"bezeichnung": "Whg. 3, 2. OG links", "strasse": "Rosenweg 5", "plz": "50667", "ort": "Köln"}


@pytest.mark.asyncio
async def test_leistungsort_nur_bei_einheit_oder_abweichender_adresse(client, hv):
    h, kunde = hv["h"], hv["kunde"]
    # Standort mit der Adresse des Kunden, keine Einheit: keine doppelte Zeile.
    gleich = await _standort(client, h, kunde, {"strasse": "kundenweg 2", "plz": "54321", "ort": "Kundenstadt"}, "Sitz")
    auftrag = await _auftrag(client, h, kunde, standort_id=gleich["id"])
    r = await _rechnung(client, h, kunde, await _vorgang(client, h, kunde, auftrag_id=auftrag["id"]))
    assert r["leistungsort"] is None and r["kunden_referenz"] is None

    # Mit Einheit trotz gleicher Adresse: Leistungsort entsteht, Bezeichnung = Einheit.
    vorgang = await _vorgang(client, h, kunde, standort_id=gleich["id"], einheit="Halle 2")
    r = await _rechnung(client, h, kunde, vorgang)
    assert r["leistungsort"]["bezeichnung"] == "Halle 2"

    # Abweichende Adresse ohne Einheit: Bezeichnung = Standort-Bezeichnung.
    vorgang = await _vorgang(client, h, kunde, standort_id=hv["standort"]["id"])
    r = await _rechnung(client, h, kunde, vorgang)
    assert r["leistungsort"]["bezeichnung"] == "Liegenschaft Rosenweg"
    assert r["leistungsort"]["strasse"] == "Rosenweg 5"

    # Ohne Standort faellt die Adresse des Vorgangs ein.
    vorgang = await _vorgang(client, h, kunde, adresse={"strasse": "Baustelle 1", "plz": "10115", "ort": "Berlin"})
    r = await _rechnung(client, h, kunde, vorgang)
    assert r["leistungsort"]["ort"] == "Berlin" and r["leistungsort"]["bezeichnung"] is None


@pytest.mark.asyncio
async def test_explizite_angaben_gewinnen_und_leeren_ist_erlaubt(client, hv):
    h = hv["h"]
    r = await _rechnung(
        client, h, hv["kunde"], hv["vorgang"], kunden_referenz="Mein Zeichen",
        leistungsort={"bezeichnung": "Hinterhaus", "ort": "Bonn"},
    )
    assert r["kunden_referenz"] == "Mein Zeichen" and _ort(r) == {"bezeichnung": "Hinterhaus", "ort": "Bonn"}

    patch = await client.patch(
        f"/api/rechnungen/{r['id']}", headers=h, json={"kunden_referenz": "  ", "leistungsort": None}
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["kunden_referenz"] is None and patch.json()["leistungsort"] is None

    patch = await client.patch(
        f"/api/rechnungen/{r['id']}", headers=h, json={"kunden_referenz": "Neu", "leistungsort": {"strasse": "Weg 1"}}
    )
    assert patch.json()["kunden_referenz"] == "Neu" and _ort(patch.json()) == {"strasse": "Weg 1"}


@pytest.mark.asyncio
async def test_aenderung_nach_versand_ist_409(client, hv):
    h = hv["h"]
    r = await _rechnung(client, h, hv["kunde"], hv["vorgang"])
    assert (await client.patch(f"/api/rechnungen/{r['id']}", headers=h, json={"status": "versendet"})).status_code == 200
    for body in ({"kunden_referenz": "X"}, {"leistungsort": None}):
        resp = await client.patch(f"/api/rechnungen/{r['id']}", headers=h, json=body)
        assert resp.status_code == 409, resp.text
    assert (await client.get(f"/api/rechnungen/{r['id']}", headers=h)).json()["kunden_referenz"] == "HV-2026-17"


@pytest.mark.asyncio
async def test_gutschrift_und_storno_uebernehmen_von_der_bezugsrechnung(client, hv):
    h = hv["h"]
    r = await _rechnung(client, h, hv["kunde"], hv["vorgang"])
    await client.patch(f"/api/rechnungen/{r['id']}", headers=h, json={"status": "versendet"})
    gutschrift = await _post(client, h, f"/api/rechnungen/{r['id']}/gutschrift", grund="Nachlass", alle=True)
    assert gutschrift["kunden_referenz"] == "HV-2026-17"
    assert gutschrift["leistungsort"]["bezeichnung"] == "Whg. 3, 2. OG links"
    r2 = await _rechnung(client, h, hv["kunde"], hv["vorgang"])
    await client.patch(f"/api/rechnungen/{r2['id']}", headers=h, json={"status": "versendet"})
    storno = await _post(client, h, f"/api/rechnungen/{r2['id']}/storno")
    assert storno["kunden_referenz"] == "HV-2026-17" and storno["leistungsort"]["ort"] == "Köln"


@pytest.mark.asyncio
async def test_angebot_vorbelegung_abschlag_und_schluss_uebernehmen_vom_angebot(client, hv):
    h = hv["h"]
    angebot = await _post(
        client, h, "/api/angebote", kunde_id=str(hv["kunde"].id), vorgang_id=hv["vorgang"]["id"], positionen=POS
    )
    assert angebot["kunden_referenz"] == "HV-2026-17"
    assert angebot["leistungsort"]["bezeichnung"] == "Whg. 3, 2. OG links"

    # Nur im Entwurf aenderbar, leeren erlaubt.
    geaendert = await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"kunden_referenz": "Neu"})
    assert geaendert.status_code == 200 and geaendert.json()["kunden_referenz"] == "Neu"
    geleert = await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"leistungsort": None})
    assert geleert.json()["leistungsort"] is None
    await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"leistungsort": {"strasse": "Weg 9"}})

    for status in ("versendet", "angenommen"):
        assert (await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"status": status})).status_code == 200
    gesperrt = await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"kunden_referenz": "Spaet"})
    assert gesperrt.status_code == 409

    abschlag = await _post(
        client, h, "/api/rechnungen/aus-angebot", angebot_id=angebot["id"], rechnungsart="abschlag",
        abschlag_prozent="30", leistungsdatum="2026-08-10",
    )
    assert abschlag["kunden_referenz"] == "Neu" and _ort(abschlag) == {"strasse": "Weg 9"}
    await client.patch(f"/api/rechnungen/{abschlag['id']}", headers=h, json={"status": "versendet"})
    schluss = await _post(
        client, h, "/api/rechnungen/aus-angebot", angebot_id=angebot["id"], rechnungsart="schluss",
        leistungsdatum="2026-08-10",
    )
    assert schluss["kunden_referenz"] == "Neu" and _ort(schluss) == {"strasse": "Weg 9"}


# --- B1: PDF und E-Rechnung --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pdf_enthaelt_ihr_zeichen_und_leistungsort(client, hv):
    h = hv["h"]
    r = await _rechnung(client, h, hv["kunde"], hv["vorgang"])
    text = _pdf_text((await client.get(f"/api/rechnungen/{r['id']}/pdf", headers=h)).content)
    assert "Ihr Zeichen" in text and "HV-2026-17" in text
    assert "Leistungsort: Rosenweg 5, 50667 Köln - Whg. 3, 2. OG links" in text.replace("\n", " ")

    angebot = await _post(
        client, h, "/api/angebote", kunde_id=str(hv["kunde"].id), vorgang_id=hv["vorgang"]["id"], positionen=POS
    )
    text = _pdf_text((await client.get(f"/api/angebote/{angebot['id']}/pdf", headers=h)).content)
    assert "Ihr Zeichen" in text and "Leistungsort: Rosenweg 5" in text.replace("\n", " ")


@pytest.mark.asyncio
async def test_pdf_ohne_angaben_hat_keine_zeilen(client, hv):
    h = hv["h"]
    r = await _rechnung(client, h, hv["kunde"])
    text = _pdf_text((await client.get(f"/api/rechnungen/{r['id']}/pdf", headers=h)).content)
    assert "Ihr Zeichen" not in text and "Leistungsort" not in text


@pytest.mark.asyncio
async def test_xml_enthaelt_bt13_und_ship_to(client, hv):
    h = hv["h"]
    r = await _rechnung(client, h, hv["kunde"], hv["vorgang"])
    versand = await client.patch(f"/api/rechnungen/{r['id']}", headers=h, json={"status": "versendet"})
    assert versand.status_code == 200 and versand.json()["xml_object_key"]
    xml = (await client.get(f"/api/rechnungen/{r['id']}/xml", headers=h)).content
    wurzel = etree.fromstring(xml)
    ns = {"ram": RAM}
    assert wurzel.xpath("//ram:BuyerOrderReferencedDocument/ram:IssuerAssignedID/text()", namespaces=ns) == ["HV-2026-17"]
    ship = "//ram:ApplicableHeaderTradeDelivery/ram:ShipToTradeParty"
    assert wurzel.xpath(f"{ship}/ram:Name/text()", namespaces=ns) == ["Whg. 3, 2. OG links"]
    assert wurzel.xpath(f"{ship}/ram:PostalTradeAddress/ram:LineOne/text()", namespaces=ns) == ["Rosenweg 5"]
    assert wurzel.xpath(f"{ship}/ram:PostalTradeAddress/ram:PostcodeCode/text()", namespaces=ns) == ["50667"]
    assert wurzel.xpath(f"{ship}/ram:PostalTradeAddress/ram:CityName/text()", namespaces=ns) == ["Köln"]
    assert wurzel.xpath(f"{ship}/ram:PostalTradeAddress/ram:CountryID/text()", namespaces=ns) == ["DE"]
    # BT-10 bleibt dem Leitweg vorbehalten.
    assert not wurzel.xpath("//ram:BuyerReference", namespaces=ns)


# --- C1: Rechnungsempfaenger ---------------------------------------------------------------------------


@pytest.fixture
async def weg(client, make_kunde, hv):
    return await make_kunde(
        mandant=hv["mandant"], name="WEG Rosenweg 5", verwaltet_von_kunde_id=hv["kunde"].id,
        **{**_KUNDE_E_RECHNUNG, "adresse": {"strasse": "c/o Hausverwaltung Nord, Kundenweg 2", "plz": "54321", "ort": "Kundenstadt"}},
    )


@pytest.mark.asyncio
async def test_rechnung_geht_an_die_weg(client, hv, weg):
    h = hv["h"]
    auftrag = await _auftrag(
        client, h, hv["kunde"], standort_id=hv["standort"]["id"], kunden_referenz="Z-1", rechnung_an_kunde_id=str(weg.id)
    )
    assert auftrag["rechnung_an_kunde_id"] == str(weg.id) and auftrag["rechnung_an"] == {
        "id": str(weg.id), "name": "WEG Rosenweg 5", "verwaltet_von_name": "Hausverwaltung Nord"
    }
    vorgang = await _vorgang(client, h, hv["kunde"], auftrag_id=auftrag["id"])

    # Auch wenn der Client den Auftraggeber schickt: der Auftrag bestimmt den Empfaenger.
    r = await _rechnung(client, h, hv["kunde"], vorgang)
    assert r["kunde_id"] == str(weg.id)
    assert r["leistungsort"]["strasse"] == "Rosenweg 5"  # weicht von der WEG-Adresse ab
    # Explizit an die WEG ist ebenfalls zulaessig.
    assert (await _rechnung(client, h, weg, vorgang))["kunde_id"] == str(weg.id)

    angebot = await _post(client, h, "/api/angebote/from-vorgang", vorgang_id=vorgang["id"])
    assert angebot["kunde_id"] == str(weg.id)


@pytest.mark.asyncio
async def test_rechnung_an_vom_projekt_und_validierung(client, hv, weg):
    h = hv["h"]
    projekt = await _post(
        client, h, "/api/projekte", name="Sanierung", kunde_id=str(hv["kunde"].id), rechnung_an_kunde_id=str(weg.id)
    )
    assert projekt["rechnung_an"]["name"] == "WEG Rosenweg 5"
    assert projekt["rechnung_an"]["verwaltet_von_name"] == "Hausverwaltung Nord"
    vorgang = await _vorgang(client, h, hv["kunde"], projekt_id=projekt["id"])
    assert (await _rechnung(client, h, hv["kunde"], vorgang))["kunde_id"] == str(weg.id)

    # Gleich dem Auftraggeber -> nichts gespeichert; unbekannter Kunde -> 422; leeren per null.
    gleich = await client.patch(
        f"/api/projekte/{projekt['id']}", headers=h, json={"rechnung_an_kunde_id": str(hv["kunde"].id)}
    )
    assert gleich.status_code == 200 and gleich.json()["rechnung_an_kunde_id"] is None
    unbekannt = await client.patch(
        f"/api/projekte/{projekt['id']}", headers=h, json={"rechnung_an_kunde_id": "00000000-0000-0000-0000-000000000001"}
    )
    assert unbekannt.status_code == 422
    auftrag = await _auftrag(client, h, hv["kunde"], rechnung_an_kunde_id=str(weg.id))
    geleert = await client.patch(f"/api/auftraege/{auftrag['id']}", headers=h, json={"rechnung_an_kunde_id": None})
    assert geleert.json()["rechnung_an"] is None


@pytest.mark.asyncio
async def test_rechnung_an_kunde_anderer_mandant_ist_422(client, make_mandant, make_kunde, hv):
    fremd = await make_kunde(mandant=await make_mandant(), name="Fremd")
    r = await client.post(
        "/api/auftraege", headers=hv["h"],
        json={"titel": "X", "kunde_id": str(hv["kunde"].id), "rechnung_an_kunde_id": str(fremd.id)},
    )
    assert r.status_code == 422


# --- C1: verwaltet von -----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verwaltet_von_zyklus_tiefe_und_liste(client, make_kunde, hv):
    h, hv_kunde = hv["h"], hv["kunde"]
    weg = await _post(client, h, "/api/kunden", name="WEG A", verwaltet_von_kunde_id=str(hv_kunde.id))
    assert weg["verwaltet_von_kunde_id"] == str(hv_kunde.id) and weg["verwaltet_von"]["name"] == "Hausverwaltung Nord"

    # Zyklus: die HV von der WEG verwalten lassen -> 422 (die HV verwaltet selbst eine WEG).
    zyklus = await client.patch(f"/api/kunden/{hv_kunde.id}", headers=h, json={"verwaltet_von_kunde_id": weg["id"]})
    assert zyklus.status_code == 422
    # Selbst-Verwaltung und Kette tiefer als eine Ebene: der Verwalter darf nicht selbst verwaltet sein.
    assert (await client.patch(f"/api/kunden/{weg['id']}", headers=h, json={"verwaltet_von_kunde_id": weg["id"]})).status_code == 422
    unter_weg = await client.post("/api/kunden", headers=h, json={"name": "Enkel", "verwaltet_von_kunde_id": weg["id"]})
    assert unter_weg.status_code == 422
    # Unbekannter Verwalter.
    assert (await client.post("/api/kunden", headers=h, json={"name": "X", "verwaltet_von_kunde_id": "00000000-0000-0000-0000-000000000001"})).status_code == 422

    liste = await client.get(f"/api/kunden/{hv_kunde.id}/verwaltete-kunden", headers=h)
    assert [k["name"] for k in liste.json()] == ["WEG A"] and liste.json()[0]["kundennummer"]
    gefiltert = await client.get(f"/api/kunden?verwaltet_von={hv_kunde.id}", headers=h)
    assert [k["id"] for k in gefiltert.json()] == [weg["id"]]
    assert gefiltert.json()[0]["verwaltet_von"]["id"] == str(hv_kunde.id)
    detail = await client.get(f"/api/kunden/{weg['id']}", headers=h)
    assert detail.json()["verwaltet_von"]["name"] == "Hausverwaltung Nord"

    # Loesen per null.
    los = await client.patch(f"/api/kunden/{weg['id']}", headers=h, json={"verwaltet_von_kunde_id": None})
    assert los.status_code == 200 and los.json()["verwaltet_von_kunde_id"] is None
    assert (await client.get(f"/api/kunden/{hv_kunde.id}/verwaltete-kunden", headers=h)).json() == []


@pytest.mark.asyncio
async def test_verwaltete_kunden_respektiert_kundenscope_des_technikers(
    client, make_mandant, make_user, make_kunde, make_kunde_zuweisung
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password=PW)
    hv_kunde = await make_kunde(mandant=mandant, name="HV")
    sichtbar = await make_kunde(mandant=mandant, name="WEG sichtbar", verwaltet_von_kunde_id=hv_kunde.id)
    await make_kunde(mandant=mandant, name="WEG fremd", verwaltet_von_kunde_id=hv_kunde.id)
    await make_kunde_zuweisung(mandant=mandant, kunde=hv_kunde, techniker=techniker)
    await make_kunde_zuweisung(mandant=mandant, kunde=sichtbar, techniker=techniker)
    h = auth_headers(await login(client, techniker.email, PW))
    resp = await client.get(f"/api/kunden/{hv_kunde.id}/verwaltete-kunden", headers=h)
    assert resp.status_code == 200, resp.text
    assert [k["name"] for k in resp.json()] == ["WEG sichtbar"]
