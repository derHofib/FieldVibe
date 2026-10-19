"""XRechnung (Migration 0109): Leitweg-ID, Profilwahl beim Versand, BR-DE-Zusatzpruefung,
E-Rechnung-Modus aus/b2b/alle. Der Schematron-Lauf gegen die BR-DE-Regeln steht in
test_e_rechnung_konformitaet.py."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pymupdf
import pytest
from lxml import etree
from sqlalchemy import text

from app.db.session import system_session
from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.services import e_invoice_service, leitweg_id
from tests.conftest import auth_headers, login
from tests.test_steuer_je_position import _migrieren, _spalten, _sync_engine

_NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
}

# Beispiel-IDs mit nachgerechneter Pruefziffer (ISO 7064 MOD 97-10).
LEITWEG = "04011000-1234512345-06"
LEITWEG_OHNE_FEIN = "991-12345-73"

_FIRMA = {
    "e_rechnung_modus": "alle",
    "adresse": {"strasse": "Musterstr. 1", "plz": "12345", "ort": "Musterstadt"},
    "ust_idnr": "DE123456789",
    "telefon": "+49 30 1234567",
    "email": "buero@mueller.example",
    "iban": "DE89 3704 0044 0532 0130 00",
    "bic": "COBADEFFXXX",
    "geschaeftsfuehrung": "Erika Mustermann",
}
_BEHOERDE = {
    "typ": "oeffentlich",
    "adresse": {"strasse": "Rathausplatz 1", "plz": "54321", "ort": "Kundenstadt"},
    "leitweg_id": LEITWEG,
}
_GEWERBE = {
    "typ": "gewerbe",
    "adresse": {"strasse": "Kundenweg 2", "plz": "54321", "ort": "Kundenstadt"},
    "ust_idnr": "DE987654321",
}
_POSITION = {"beschreibung": "Wartung", "menge": "2", "einzelpreis": "50"}


async def _admin(client, make_mandant, make_user, make_kunde, *, firmendaten=_FIRMA, **kunde_kw):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, **kunde_kw)
    token = await login(client, admin.email, "pw-123456")
    if firmendaten is not None:
        resp = await client.patch(
            "/api/mandant/einstellungen", headers=auth_headers(token), json={"firmendaten": firmendaten}
        )
        assert resp.status_code == 200, resp.text
    return token, kunde


async def _entwurf(client, token, kunde) -> dict:
    resp = await client.post(
        "/api/rechnungen",
        headers=auth_headers(token),
        json={
            "kunde_id": str(kunde.id),
            "mwst_satz": "19.00",
            "leistungsdatum": "2026-08-10",
            "positionen": [_POSITION],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _versenden(client, token, rechnung_id):
    return await client.patch(
        f"/api/rechnungen/{rechnung_id}", headers=auth_headers(token), json={"status": "versendet"}
    )


async def _versendet(client, token, kunde) -> dict:
    rechnung = await _entwurf(client, token, kunde)
    resp = await _versenden(client, token, rechnung["id"])
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _xml(client, token, rechnung_id):
    return await client.get(f"/api/rechnungen/{rechnung_id}/xml", headers=auth_headers(token))


def _wert(xml: bytes, pfad: str) -> list[str]:
    return [e.text for e in etree.fromstring(xml).xpath(pfad, namespaces=_NS)]


# --- Leitweg-ID ---------------------------------------------------------------------


def test_leitweg_pruefziffer_der_beispiele():
    assert leitweg_id.pruefziffer("991" + "12345") == "73"
    assert leitweg_id.pruefziffer("04011000" + "1234512345") == "06"


@pytest.mark.parametrize(
    "wert",
    [
        LEITWEG,
        LEITWEG_OHNE_FEIN,
        "  04011000-1234512345-06 ",
        "04011000 - 1234512345 - 06",
        "04011000-1234512345-06".lower(),
    ],
)
def test_leitweg_gueltig_wird_normalisiert(wert):
    assert leitweg_id.normalisiere_und_pruefe(wert) in (LEITWEG, LEITWEG_OHNE_FEIN)


@pytest.mark.parametrize("wert", [None, "", "   "])
def test_leitweg_leer_wird_none(wert):
    assert leitweg_id.normalisiere_und_pruefe(wert) is None


def test_leitweg_mit_buchstaben_in_der_feinadressierung():
    grob_fein = "99ABC123"
    ziffern = leitweg_id.pruefziffer(grob_fein)
    assert leitweg_id.normalisiere_und_pruefe(f"99-abc123-{ziffern}") == f"99-ABC123-{ziffern}"


@pytest.mark.parametrize(
    "wert, teil",
    [
        ("04011000-1234512345-07", "Prüfziffer"),  # falsche Pruefziffer
        ("991-12345-74", "Prüfziffer"),
        ("9-12345-73", "Format"),  # Grobadressierung zu kurz
        ("1234567890123-12345-73", "Format"),  # 13 Ziffern
        ("991-" + "A" * 31 + "-73", "Format"),  # Feinadressierung zu lang
        ("991-12_45-73", "Format"),  # Sonderzeichen
        ("991-12345", "Format"),  # keine Pruefziffer
        ("991-12345-7", "Format"),  # einstellige Pruefziffer
        ("99A-12345-73", "Format"),  # Buchstabe in der Grobadressierung
        ("hallo", "Format"),
    ],
)
def test_leitweg_ungueltig(wert, teil):
    with pytest.raises(ValueError, match=teil):
        leitweg_id.normalisiere_und_pruefe(wert)


# --- Kunde: API ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kunde_anlegen_und_aendern_mit_leitweg_id(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    h = auth_headers(await login(client, admin.email, "pw-123456"))

    angelegt = await client.post(
        "/api/kunden",
        headers=h,
        json={"name": "Stadt Musterstadt", "typ": "oeffentlich", "leitweg_id": " 04011000-1234512345-06 "},
    )
    assert angelegt.status_code == 201, angelegt.text
    assert angelegt.json()["leitweg_id"] == LEITWEG
    assert angelegt.json()["e_rechnung_format"] is None
    kunde_id = angelegt.json()["id"]

    geaendert = await client.patch(f"/api/kunden/{kunde_id}", headers=h, json={"e_rechnung_format": "zugferd"})
    assert geaendert.status_code == 200
    assert geaendert.json()["e_rechnung_format"] == "zugferd"
    assert geaendert.json()["leitweg_id"] == LEITWEG  # unberuehrt

    geleert = await client.patch(
        f"/api/kunden/{kunde_id}", headers=h, json={"leitweg_id": "", "e_rechnung_format": None}
    )
    assert geleert.status_code == 200
    assert geleert.json()["leitweg_id"] is None and geleert.json()["e_rechnung_format"] is None
    assert (await client.get(f"/api/kunden/{kunde_id}", headers=h)).json()["leitweg_id"] is None


@pytest.mark.asyncio
async def test_kunde_mit_ungueltiger_leitweg_id_wird_mit_422_abgelehnt(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    h = auth_headers(await login(client, admin.email, "pw-123456"))

    angelegt = await client.post("/api/kunden", headers=h, json={"name": "X", "leitweg_id": "04011000-1234512345-99"})
    assert angelegt.status_code == 422
    assert "Prüfziffer" in angelegt.text
    geaendert = await client.patch(f"/api/kunden/{kunde.id}", headers=h, json={"leitweg_id": "kaputt"})
    assert geaendert.status_code == 422
    assert "Format" in geaendert.text
    format_falsch = await client.patch(f"/api/kunden/{kunde.id}", headers=h, json={"e_rechnung_format": "pdf"})
    assert format_falsch.status_code == 422


# --- Profilwahl ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "format_, leitweg, erwartet",
    [
        (None, None, "en16931"),
        (None, "", "en16931"),
        (None, LEITWEG, "xrechnung"),  # Automatik: Leitweg-ID -> XRechnung
        ("zugferd", LEITWEG, "en16931"),  # explizit gewinnt
        ("xrechnung", None, "xrechnung"),
        ("xrechnung", LEITWEG, "xrechnung"),
        ("zugferd", None, "en16931"),
    ],
)
def test_profil_fuer(format_, leitweg, erwartet):
    assert e_invoice_service.profil_fuer(Kunde(e_rechnung_format=format_, leitweg_id=leitweg)) == erwartet


@pytest.mark.parametrize(
    "kunde, gewerblich",
    [
        (Kunde(typ="gewerbe"), True),
        (Kunde(typ="oeffentlich"), True),
        (Kunde(typ="hausverwaltung"), True),
        (Kunde(typ="privat"), False),
        (Kunde(typ=None), False),
        (Kunde(typ=None, ust_idnr="DE987654321"), True),
        (Kunde(typ="privat", ust_idnr="  "), False),
        (Kunde(typ=None, leitweg_id=LEITWEG), True),
    ],
)
def test_kunde_ist_gewerblich(kunde, gewerblich):
    assert kunde.ist_gewerblich is gewerblich


@pytest.mark.parametrize(
    "firmendaten, erwartet",
    [
        ({}, "aus"),
        ({"e_rechnung_aktiv": True}, "alle"),
        ({"e_rechnung_aktiv": False}, "aus"),
        ({"e_rechnung_modus": "b2b", "e_rechnung_aktiv": True}, "b2b"),
        ({"e_rechnung_modus": "aus", "e_rechnung_aktiv": True}, "aus"),
        ({"e_rechnung_modus": "unsinn", "e_rechnung_aktiv": True}, "alle"),
        (None, "aus"),
    ],
)
def test_e_rechnung_modus_fallback(firmendaten, erwartet):
    assert e_invoice_service.e_rechnung_modus(firmendaten) == erwartet


# --- Versand als XRechnung ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_versand_an_behoerde_erzeugt_xrechnung(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde, **_BEHOERDE)
    rechnung = await _versendet(client, token, kunde)

    assert rechnung["e_rechnung_profil"] == "xrechnung"
    assert rechnung["leitweg_id"] == LEITWEG
    assert rechnung["xml_object_key"] is not None

    antwort = await _xml(client, token, rechnung["id"])
    assert antwort.status_code == 200
    assert f'filename="{rechnung["rechnungsnummer"]}-xrechnung.xml"' in antwort.headers["content-disposition"]
    xml = antwort.content
    kennung = "//rsm:ExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID"
    assert _wert(xml, kennung) == ["urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"]
    agreement = "//ram:ApplicableHeaderTradeAgreement"
    assert _wert(xml, f"{agreement}/ram:BuyerReference") == [LEITWEG]  # BT-10
    kontakt = f"{agreement}/ram:SellerTradeParty/ram:DefinedTradeContact"
    assert _wert(xml, f"{kontakt}/ram:PersonName") == ["Erika Mustermann"]
    assert _wert(xml, f"{kontakt}/ram:TelephoneUniversalCommunication/ram:CompleteNumber") == ["+49 30 1234567"]
    assert _wert(xml, f"{kontakt}/ram:EmailURIUniversalCommunication/ram:URIID") == ["buero@mueller.example"]
    zahlung = "//ram:SpecifiedTradeSettlementPaymentMeans"
    assert _wert(xml, f"{zahlung}/ram:TypeCode") == ["58"]
    assert _wert(xml, f"{zahlung}/ram:PayeePartyCreditorFinancialAccount/ram:IBANID") == ["DE89370400440532013000"]
    assert _wert(xml, f"{zahlung}/ram:PayeeSpecifiedCreditorFinancialInstitution/ram:BICID") == ["COBADEFFXXX"]
    buyer_adresse = etree.fromstring(xml).xpath(
        f"{agreement}/ram:BuyerTradeParty/ram:URIUniversalCommunication/ram:URIID", namespaces=_NS
    )
    assert buyer_adresse[0].get("schemeID") == "0204" and buyer_adresse[0].text == LEITWEG


@pytest.mark.asyncio
async def test_xrechnung_pdf_ist_hybrid_mit_eingebetteter_xml(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde, **_BEHOERDE)
    rechnung = await _versendet(client, token, kunde)

    pdf = await client.get(f"/api/rechnungen/{rechnung['id']}/pdf", headers=auth_headers(token))
    dok = pymupdf.open(stream=pdf.content, filetype="pdf")
    assert dok.embfile_names() == ["factur-x.xml"]
    eingebettet = dok.embfile_get("factur-x.xml")
    assert eingebettet == (await _xml(client, token, rechnung["id"])).content
    assert "<fx:ConformanceLevel>XRECHNUNG</fx:ConformanceLevel>" in dok.get_xml_metadata()


@pytest.mark.asyncio
async def test_snapshot_bleibt_trotz_spaeterer_kundenaenderung(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde, **_BEHOERDE)
    rechnung = await _versendet(client, token, kunde)
    h = auth_headers(token)

    geaendert = await client.patch(
        f"/api/kunden/{kunde.id}", headers=h, json={"leitweg_id": LEITWEG_OHNE_FEIN, "e_rechnung_format": "zugferd"}
    )
    assert geaendert.status_code == 200
    gelesen = (await client.get(f"/api/rechnungen/{rechnung['id']}", headers=h)).json()
    assert gelesen["e_rechnung_profil"] == "xrechnung"
    assert gelesen["leitweg_id"] == LEITWEG
    assert _wert((await _xml(client, token, rechnung["id"])).content, "//ram:BuyerReference") == [LEITWEG]


@pytest.mark.asyncio
async def test_entwurf_hat_noch_kein_profil(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde, **_BEHOERDE)
    rechnung = await _entwurf(client, token, kunde)
    assert rechnung["e_rechnung_profil"] is None and rechnung["leitweg_id"] is None


@pytest.mark.asyncio
async def test_ohne_leitweg_id_bleibt_es_bei_zugferd(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde, **_GEWERBE)
    rechnung = await _versendet(client, token, kunde)
    assert rechnung["e_rechnung_profil"] == "en16931" and rechnung["leitweg_id"] is None
    xml = (await _xml(client, token, rechnung["id"])).content
    assert _wert(xml, "//ram:GuidelineSpecifiedDocumentContextParameter/ram:ID") == ["urn:cen.eu:en16931:2017"]
    assert _wert(xml, "//ram:BuyerReference") == []
    assert _wert(xml, "//ram:SpecifiedTradeSettlementPaymentMeans") == []
    assert 'filename="factur-x.xml"' in (await _xml(client, token, rechnung["id"])).headers["content-disposition"]


@pytest.mark.asyncio
async def test_zugferd_erzwungen_traegt_leitweg_id_als_kaeuferreferenz(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(
        client,
        make_mandant,
        make_user,
        make_kunde,
        **{**_BEHOERDE, "e_rechnung_format": "zugferd", "ust_idnr": "DE987654321"},
    )
    rechnung = await _versendet(client, token, kunde)
    assert rechnung["e_rechnung_profil"] == "en16931" and rechnung["leitweg_id"] == LEITWEG
    xml = (await _xml(client, token, rechnung["id"])).content
    assert _wert(xml, "//ram:GuidelineSpecifiedDocumentContextParameter/ram:ID") == ["urn:cen.eu:en16931:2017"]
    assert _wert(xml, "//ram:BuyerReference") == [LEITWEG]


@pytest.mark.asyncio
async def test_xrechnung_ohne_geschaeftsfuehrung_nimmt_firmenname_als_abteilung(
    client, make_mandant, make_user, make_kunde
):
    firma = {k: v for k, v in _FIRMA.items() if k != "geschaeftsfuehrung"}
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde, firmendaten=firma, **_BEHOERDE)
    rechnung = await _versendet(client, token, kunde)
    xml = (await _xml(client, token, rechnung["id"])).content
    kontakt = "//ram:SellerTradeParty/ram:DefinedTradeContact"
    assert _wert(xml, f"{kontakt}/ram:PersonName") == []
    assert len(_wert(xml, f"{kontakt}/ram:DepartmentName")) == 1


@pytest.mark.asyncio
async def test_behoerde_ohne_ust_idnr_ist_mit_xrechnung_versendbar(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde, **_BEHOERDE)
    assert kunde.ust_idnr is None
    assert (await _versenden(client, token, (await _entwurf(client, token, kunde))["id"])).status_code == 200


@pytest.mark.asyncio
async def test_behoerde_ohne_ust_idnr_und_ohne_xrechnung_braucht_weiter_die_ust_idnr(
    client, make_mandant, make_user, make_kunde
):
    token, kunde = await _admin(
        client, make_mandant, make_user, make_kunde, **{**_BEHOERDE, "e_rechnung_format": "zugferd"}
    )
    antwort = await _versenden(client, token, (await _entwurf(client, token, kunde))["id"])
    assert antwort.status_code == 422
    assert "USt-IdNr. des Kunden fehlt" in antwort.json()["detail"]


@pytest.mark.asyncio
async def test_typcode_abschlag_xrechnung_ist_326_zugferd_bleibt_386(client, make_mandant, make_user, make_kunde):
    # BR-DE-17: die XRechnung kennt 386 nicht, ZUGFeRD (EN 16931) schon.
    ergebnisse = {}
    for name, kunde_kw in (("xrechnung", _BEHOERDE), ("zugferd", _GEWERBE)):
        token, kunde = await _admin(client, make_mandant, make_user, make_kunde, **kunde_kw)
        rechnung = await client.post(
            "/api/rechnungen",
            headers=auth_headers(token),
            json={
                "kunde_id": str(kunde.id),
                "rechnungsart": "abschlag",
                "mwst_satz": "19.00",
                "leistungsdatum": "2026-08-10",
                "positionen": [{"beschreibung": "Abschlag", "einzelpreis": "100"}],
            },
        )
        assert rechnung.status_code == 201, rechnung.text
        versendet = await _versenden(client, token, rechnung.json()["id"])
        assert versendet.status_code == 200, versendet.text
        xml = (await _xml(client, token, rechnung.json()["id"])).content
        ergebnisse[name] = _wert(xml, "//rsm:ExchangedDocument/ram:TypeCode")
    assert ergebnisse == {"xrechnung": ["326"], "zugferd": ["386"]}


@pytest.mark.asyncio
async def test_storno_verweist_nur_bei_xrechnung_auf_die_ursprungsrechnung(
    client, make_mandant, make_user, make_kunde
):
    for kunde_kw, erwartet in ((_BEHOERDE, True), (_GEWERBE, False)):
        token, kunde = await _admin(client, make_mandant, make_user, make_kunde, **kunde_kw)
        original = await _versendet(client, token, kunde)
        storno = await client.post(f"/api/rechnungen/{original['id']}/storno", headers=auth_headers(token))
        assert storno.status_code == 201, storno.text
        xml = (await _xml(client, token, storno.json()["id"])).content
        referenz = _wert(xml, "//ram:InvoiceReferencedDocument/ram:IssuerAssignedID")
        assert referenz == ([original["rechnungsnummer"]] if erwartet else [])


# --- Versandpruefung ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_versandpruefung_listet_alle_fehlenden_xrechnung_angaben(client, make_mandant, make_user, make_kunde):
    firma = {
        "e_rechnung_modus": "alle",
        "adresse": {"strasse": "Musterstr. 1", "plz": "12345", "ort": "Musterstadt"},
        "ust_idnr": "DE123456789",
    }
    token, kunde = await _admin(
        client, make_mandant, make_user, make_kunde, firmendaten=firma, **{**_GEWERBE, "e_rechnung_format": "xrechnung"}
    )
    rechnung = await _entwurf(client, token, kunde)
    antwort = await _versenden(client, token, rechnung["id"])

    assert antwort.status_code == 422
    detail = antwort.json()["detail"]
    for teil in ("Leitweg-ID des Kunden fehlt", "Telefonnummer des Mandanten fehlt", "E-Mail-Adresse des Mandanten fehlt", "IBAN des Mandanten fehlt"):
        assert teil in detail
    # kein stiller Fallback: Entwurf unberuehrt, nichts archiviert
    gelesen = (await client.get(f"/api/rechnungen/{rechnung['id']}", headers=auth_headers(token))).json()
    assert gelesen["status"] == "entwurf" and gelesen["xml_object_key"] is None and gelesen["e_rechnung_profil"] is None


@pytest.mark.asyncio
async def test_versandpruefung_meldet_ungueltige_kontaktdaten_und_iban(client, make_mandant, make_user, make_kunde):
    firma = {**_FIRMA, "telefon": "12", "email": "keine-adresse", "iban": "DE00 0000 0000 0000 0000 00"}
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde, firmendaten=firma, **_BEHOERDE)
    antwort = await _versenden(client, token, (await _entwurf(client, token, kunde))["id"])
    assert antwort.status_code == 422
    detail = antwort.json()["detail"]
    assert "mindestens drei Ziffern" in detail
    assert "E-Mail-Adresse des Mandanten ist ungültig" in detail
    assert "IBAN des Mandanten ist ungültig" in detail


def test_iban_pruefsumme():
    assert e_invoice_service.iban_gueltig("DE89 3704 0044 0532 0130 00")
    assert e_invoice_service.iban_gueltig("de89370400440532013000")
    assert not e_invoice_service.iban_gueltig("DE89 3704 0044 0532 0130 01")
    assert not e_invoice_service.iban_gueltig("12345")


# --- E-Rechnung-Modus --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_modus_aus_erzeugt_nie_xml(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(
        client, make_mandant, make_user, make_kunde, firmendaten={**_FIRMA, "e_rechnung_modus": "aus"}, **_BEHOERDE
    )
    rechnung = await _versendet(client, token, kunde)
    assert rechnung["xml_object_key"] is None and rechnung["e_rechnung_profil"] is None


@pytest.mark.asyncio
async def test_modus_b2b_nur_fuer_gewerbliche_kunden(client, make_mandant, make_user, make_kunde):
    firma = {"e_rechnung_modus": "b2b", "adresse": _FIRMA["adresse"], "ust_idnr": "DE123456789"}
    token, gewerbe = await _admin(client, make_mandant, make_user, make_kunde, firmendaten=firma, **_GEWERBE)
    h = auth_headers(token)
    mandant = SimpleNamespace(id=gewerbe.mandant_id)  # make_kunde braucht nur die id
    privat = await make_kunde(mandant=mandant, typ="privat", name="Privat")
    ohne_typ = await make_kunde(mandant=mandant, name="Ohne Typ")

    assert (await _versendet(client, token, gewerbe))["xml_object_key"] is not None
    for kunde in (privat, ohne_typ):
        # Privatkunde ohne Anschrift: ohne E-Rechnung kein 422, normales PDF
        rechnung = await _versendet(client, token, kunde)
        assert rechnung["xml_object_key"] is None and rechnung["e_rechnung_profil"] is None
        pdf = await client.get(f"/api/rechnungen/{rechnung['id']}/pdf", headers=h)
        assert pdf.status_code == 200 and pymupdf.open(stream=pdf.content, filetype="pdf").embfile_names() == []


@pytest.mark.asyncio
async def test_modus_alle_prueft_auch_privatkunden(client, make_mandant, make_user, make_kunde):
    firma = {"e_rechnung_modus": "alle", "adresse": _FIRMA["adresse"], "ust_idnr": "DE123456789"}
    token, privat = await _admin(client, make_mandant, make_user, make_kunde, firmendaten=firma, typ="privat")
    rechnung = await _entwurf(client, token, privat)
    antwort = await _versenden(client, token, rechnung["id"])
    assert antwort.status_code == 422
    assert "Anschrift des Kunden unvollstaendig" in antwort.json()["detail"]


@pytest.mark.asyncio
async def test_modus_b2b_und_leitweg_id_ohne_typ_gilt_als_gewerblich(client, make_mandant, make_user, make_kunde):
    firma = {**_FIRMA, "e_rechnung_modus": "b2b"}
    token, kunde = await _admin(
        client,
        make_mandant,
        make_user,
        make_kunde,
        firmendaten=firma,
        adresse=_BEHOERDE["adresse"],
        leitweg_id=LEITWEG,
    )
    assert (await _versendet(client, token, kunde))["e_rechnung_profil"] == "xrechnung"


@pytest.mark.asyncio
async def test_einstellungen_leiten_aktiv_und_modus_ab(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    h = auth_headers(await login(client, admin.email, "pw-123456"))

    async def speichern(firmendaten):
        return await client.patch("/api/mandant/einstellungen", headers=h, json={"firmendaten": firmendaten})

    antwort = await speichern({"e_rechnung_modus": "b2b"})
    assert antwort.status_code == 200
    assert antwort.json()["firmendaten"]["e_rechnung_modus"] == "b2b"
    assert antwort.json()["firmendaten"]["e_rechnung_aktiv"] is True

    antwort = await speichern({"e_rechnung_modus": "aus"})
    assert antwort.json()["firmendaten"]["e_rechnung_aktiv"] is False

    # aelterer Client schickt nur e_rechnung_aktiv
    antwort = await speichern({"e_rechnung_aktiv": True})
    assert antwort.json()["firmendaten"]["e_rechnung_modus"] == "alle"
    antwort = await speichern({"e_rechnung_aktiv": False})
    assert antwort.json()["firmendaten"]["e_rechnung_modus"] == "aus"

    # andere Formulare lassen den Modus unberuehrt
    await speichern({"e_rechnung_modus": "b2b"})
    antwort = await speichern({"telefon": "0123 456789"})
    assert antwort.json()["firmendaten"]["e_rechnung_modus"] == "b2b"

    assert (await speichern({"e_rechnung_modus": "immer"})).status_code == 422
    assert (await speichern({"privatkunden_hinweise": "ja"})).status_code == 422
    assert (await speichern({"privatkunden_hinweise": False})).json()["firmendaten"]["privatkunden_hinweise"] is False


@pytest.mark.asyncio
async def test_neuer_mandant_startet_mit_modus_b2b(client, make_user):
    admin = await make_user(mandant=None, role="super_admin", password="admin-pass-1")
    token = await login(client, admin.email, "admin-pass-1")
    angelegt = await client.post(
        "/api/admin/mandanten", headers=auth_headers(token), json={"name": "Neu GmbH", "slug": "neu-gmbh-xr"}
    )
    assert angelegt.status_code == 201
    async with system_session() as session:
        mandant = await session.get(Mandant, uuid.UUID(angelegt.json()["id"]))
        assert mandant.firmendaten["e_rechnung_modus"] == "b2b"
        assert e_invoice_service.e_rechnung_modus(mandant.firmendaten) == "b2b"


# --- E-Mail-Versand ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_haengt_bei_xrechnung_die_xml_an(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde, **_BEHOERDE)
    rechnung = await _versendet(client, token, kunde)
    with patch("app.services.email_service.send_email", new_callable=AsyncMock) as versand:
        antwort = await client.post(
            f"/api/rechnungen/{rechnung['id']}/email",
            headers=auth_headers(token),
            json={"empfaenger": "rechnungseingang@stadt.example"},
        )
    assert antwort.status_code == 201, antwort.text
    kwargs = versand.call_args.kwargs
    assert kwargs["attachment"][0] == f"{rechnung['rechnungsnummer']}.pdf"
    [(name, inhalt, mime)] = kwargs["weitere_anhaenge"]
    assert name == f"{rechnung['rechnungsnummer']}-xrechnung.xml" and mime == "application/xml"
    assert inhalt == (await _xml(client, token, rechnung["id"])).content


@pytest.mark.asyncio
async def test_email_bei_zugferd_nur_pdf(client, make_mandant, make_user, make_kunde):
    token, kunde = await _admin(client, make_mandant, make_user, make_kunde, **_GEWERBE)
    rechnung = await _versendet(client, token, kunde)
    with patch("app.services.email_service.send_email", new_callable=AsyncMock) as versand:
        antwort = await client.post(
            f"/api/rechnungen/{rechnung['id']}/email", headers=auth_headers(token), json={"empfaenger": "a@b.example"}
        )
    assert antwort.status_code == 201
    assert versand.call_args.kwargs["weitere_anhaenge"] == []


# --- Migration 0109 -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_migration_0109_up_down_up_mit_modus_backfill(make_mandant, make_user, make_kunde):
    aktiv = await make_mandant()
    user = await make_user(mandant=aktiv, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=aktiv)
    inaktiv = await make_mandant()
    leer = await make_mandant()
    engine = _sync_engine()
    try:
        await _migrieren("downgrade", "0108")
        assert not {"leitweg_id", "e_rechnung_format"} & set(_spalten(engine, "kunden"))
        assert not {"leitweg_id", "e_rechnung_profil"} & set(_spalten(engine, "rechnungen"))

        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            for mandant, daten in (
                (aktiv, '{"e_rechnung_aktiv": true, "telefon": "1"}'),
                (inaktiv, '{"e_rechnung_aktiv": false}'),
                (leer, "{}"),
            ):
                conn.execute(
                    text("UPDATE mandanten SET firmendaten = CAST(:d AS jsonb) WHERE id = :m"),
                    {"d": daten, "m": mandant.id},
                )

        await _migrieren("upgrade", "head")

        assert {"leitweg_id", "e_rechnung_format"} <= set(_spalten(engine, "kunden"))
        assert {"leitweg_id", "e_rechnung_profil"} <= set(_spalten(engine, "rechnungen"))
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            modi = {
                m.id: conn.execute(
                    text("SELECT firmendaten FROM mandanten WHERE id = :m"), {"m": m.id}
                ).scalar_one()
                for m in (aktiv, inaktiv, leer)
            }
            assert modi[aktiv.id]["e_rechnung_modus"] == "alle" and modi[aktiv.id]["telefon"] == "1"
            assert modi[aktiv.id]["e_rechnung_aktiv"] is True
            assert modi[inaktiv.id]["e_rechnung_modus"] == "aus"
            assert modi[leer.id]["e_rechnung_modus"] == "aus"
            rechnung_id = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO rechnungen (id, mandant_id, kunde_id, rechnungsnummer, betrag_netto, mwst_satz, "
                    "erstellt_von) VALUES (:id, :m, :k, 'R-MIG-0109', 0, 19, :u)"
                ),
                {"id": rechnung_id, "m": aktiv.id, "k": kunde.id, "u": user.id},
            )
        # Eine verletzte Constraint macht die Transaktion unbrauchbar: je Pruefung eine eigene.
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            with pytest.raises(Exception, match="ck_kunden_e_rechnung_format_valid"):
                conn.execute(text("UPDATE kunden SET e_rechnung_format = 'pdf' WHERE id = :id"), {"id": kunde.id})
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            for tabelle in ("kunden", "rechnungen"):
                relrls, relforce = conn.execute(
                    text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :t"), {"t": tabelle}
                ).one()
                assert relrls and relforce, tabelle
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            with pytest.raises(Exception, match="ck_rechnungen_e_rechnung_profil_valid"):
                conn.execute(text("UPDATE rechnungen SET e_rechnung_profil = 'pdf' WHERE id = :id"), {"id": rechnung_id})

        # Abwaerts: der Modus-Schluessel verschwindet wieder, e_rechnung_aktiv bleibt.
        await _migrieren("downgrade", "0108")
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            firmendaten = conn.execute(
                text("SELECT firmendaten FROM mandanten WHERE id = :m"), {"m": aktiv.id}
            ).scalar_one()
            assert "e_rechnung_modus" not in firmendaten and firmendaten["e_rechnung_aktiv"] is True
    finally:
        await _migrieren("upgrade", "head")
        engine.dispose()
