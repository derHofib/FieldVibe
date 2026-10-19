from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.rechnung import Rechnung, RechnungPosition
from app.services import e_invoice_service


def _mandant(**firmendaten_overrides) -> Mandant:
    firmendaten = {
        "adresse": {"strasse": "Musterstr. 1", "plz": "12345", "ort": "Musterstadt"},
        "ust_idnr": "DE123456789",
    }
    firmendaten.update(firmendaten_overrides)
    return Mandant(id=uuid4(), name="Elektro Mueller GmbH", slug="mueller", firmendaten=firmendaten)


def _kunde(**overrides) -> Kunde:
    defaults = {
        "id": uuid4(),
        "kundennummer": "K-1",
        "name": "Cafe Sonnenschein",
        "typ": "gewerbe",
        "ansprechpartner": [],
        "adresse": {"strasse": "Kundenweg 2", "plz": "54321", "ort": "Kundenstadt"},
        "ust_idnr": "DE987654321",
        "portal_slug": uuid4().hex,
    }
    defaults.update(overrides)
    return Kunde(**defaults)


def _rechnung(**overrides) -> Rechnung:
    defaults = {
        "id": uuid4(),
        "kunde_id": uuid4(),
        "rechnungsnummer": "R-00001",
        "leistungsdatum": date(2026, 8, 10),
        "betrag_netto": Decimal("300.00"),
        "mwst_satz": Decimal("19.00"),
        "status": "entwurf",
        "erstellt_von": uuid4(),
        "ist_storno": False,
        "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return Rechnung(**defaults)


def _position(**overrides) -> RechnungPosition:
    defaults = {
        "position": 1,
        "beschreibung": "Elektroinstallation",
        "menge": Decimal("1"),
        "einheit": "Stk",
        "einzelpreis": Decimal("300.00"),
    }
    defaults.update(overrides)
    return RechnungPosition(**defaults)


def test_vollstaendigkeit_ok_mit_allen_pflichtfeldern():
    probleme = e_invoice_service.pruefe_en16931_vollstaendigkeit(_mandant(), _rechnung(), _kunde(), [_position()])
    assert probleme == []


def test_vollstaendigkeit_fehlende_ust_idnr_bei_gewerbe_kunde():
    kunde = _kunde(typ="gewerbe", ust_idnr=None)
    probleme = e_invoice_service.pruefe_en16931_vollstaendigkeit(_mandant(), _rechnung(), kunde, [_position()])
    assert any("USt-IdNr. des Kunden" in p for p in probleme)


def test_vollstaendigkeit_privat_kunde_braucht_keine_ust_idnr():
    kunde = _kunde(typ="privat", ust_idnr=None)
    probleme = e_invoice_service.pruefe_en16931_vollstaendigkeit(_mandant(), _rechnung(), kunde, [_position()])
    assert probleme == []


def test_vollstaendigkeit_fehlende_seller_adresse():
    mandant = _mandant(adresse={})
    probleme = e_invoice_service.pruefe_en16931_vollstaendigkeit(mandant, _rechnung(), _kunde(), [_position()])
    assert any("Anschrift des Mandanten" in p for p in probleme)


def test_vollstaendigkeit_kleinunternehmer_ohne_ust_idnr_oder_steuernummer():
    mandant = _mandant(ust_idnr=None, ist_kleinunternehmer=True)
    probleme = e_invoice_service.pruefe_en16931_vollstaendigkeit(mandant, _rechnung(), _kunde(), [_position()])
    assert any("USt-IdNr." in p and "Mandanten" in p for p in probleme)


def test_vollstaendigkeit_fehlendes_leistungsdatum():
    probleme = e_invoice_service.pruefe_en16931_vollstaendigkeit(
        _mandant(), _rechnung(leistungsdatum=None), _kunde(), [_position()]
    )
    assert any("Leistungsdatum" in p for p in probleme)


@pytest.mark.parametrize("mit_positionen", [True, False])
def test_cii_xml_enthaelt_rechnungsnummer_und_betraege(mit_positionen):
    rechnung = _rechnung()
    positionen = [_position()] if mit_positionen else []
    dokument = e_invoice_service.baue_cii_dokument(
        _mandant(), rechnung, _kunde(), positionen, Decimal("300.00"), Decimal("357.00")
    )
    xml = e_invoice_service.cii_xml_bytes(dokument)
    text = xml.decode("utf-8")
    assert rechnung.rechnungsnummer in text
    assert "300.00" in text
    assert "357.00" in text
    assert "57.00" in text  # Steuerbetrag


def test_kleinunternehmer_exemption_code_und_text():
    mandant = _mandant(ist_kleinunternehmer=True)
    rechnung = _rechnung(mwst_satz=Decimal("19.00"))
    dokument = e_invoice_service.baue_cii_dokument(
        mandant, rechnung, _kunde(), [_position()], Decimal("300.00"), Decimal("300.00")
    )
    xml = e_invoice_service.cii_xml_bytes(dokument).decode("utf-8")
    assert f"<ram:CategoryCode>{e_invoice_service.KLEINUNTERNEHMER_VAT_EXEMPTION_CODE}</ram:CategoryCode>" in xml
    assert e_invoice_service.KLEINUNTERNEHMER_VAT_EXEMPTION_REASON in xml


def test_storno_rechnung_hat_typecode_384():
    rechnung = _rechnung(ist_storno=True)
    dokument = e_invoice_service.baue_cii_dokument(
        _mandant(), rechnung, _kunde(), [_position()], Decimal("300.00"), Decimal("357.00")
    )
    xml = e_invoice_service.cii_xml_bytes(dokument).decode("utf-8")
    assert "<ram:TypeCode>384</ram:TypeCode>" in xml


def test_baue_hybrid_pdf_bettet_xml_ein():
    from app.services import pdf_service

    mandant = _mandant()
    rechnung = _rechnung()
    kunde = _kunde()
    positionen = [_position()]

    pdf_bytes = pdf_service.generate_rechnung_pdf(mandant, rechnung, kunde, positionen, pdfa_output_intent=True)
    assert pdf_bytes.startswith(b"%PDF")

    dokument = e_invoice_service.baue_cii_dokument(
        mandant, rechnung, kunde, positionen, Decimal("300.00"), Decimal("357.00")
    )
    xml_bytes = e_invoice_service.cii_xml_bytes(dokument)

    hybrid_bytes = e_invoice_service.baue_hybrid_pdf(pdf_bytes, xml_bytes)
    assert hybrid_bytes.startswith(b"%PDF")
    assert b"factur-x.xml" in hybrid_bytes
    assert len(hybrid_bytes) > len(pdf_bytes)


def test_waehrung_nur_am_steuerbetrag():
    # CII-DT-031 der EN-16931-Geschaeftsregeln: currencyID nur am Steuerbetrag (BT-110).
    dokument = e_invoice_service.baue_cii_dokument(
        _mandant(), _rechnung(), _kunde(), [_position()], Decimal("300.00"), Decimal("357.00")
    )
    xml = e_invoice_service.cii_xml_bytes(dokument).decode("utf-8")
    assert '<ram:TaxTotalAmount currencyID="EUR">57.00</ram:TaxTotalAmount>' in xml
    assert "currencyID" not in xml.replace('<ram:TaxTotalAmount currencyID="EUR">', "")


def _verkaeufer_ids(xml: bytes) -> list[tuple[str | None, str]]:
    from lxml import etree

    ns = {"ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"}
    wurzel = etree.fromstring(xml)
    verkaeufer = wurzel.xpath("//ram:SellerTradeParty", namespaces=ns)[0]
    kennung = [(None, e.text) for e in verkaeufer.xpath("ram:ID", namespaces=ns)]
    steuer = [(e.get("schemeID"), e.text) for e in verkaeufer.xpath("ram:SpecifiedTaxRegistration/ram:ID", namespaces=ns)]
    return kennung + steuer


def test_verkaeufer_nur_mit_steuernummer_bekommt_verkaeuferkennung():
    # BR-CO-26: BT-29/BT-30/BT-31 muessen vorhanden sein, die Steuernummer (BT-32) zaehlt nicht.
    mandant = _mandant(ust_idnr=None, steuernummer="12/345/67890", ist_kleinunternehmer=True)
    dokument = e_invoice_service.baue_cii_dokument(
        mandant, _rechnung(), _kunde(), [_position()], Decimal("300.00"), Decimal("300.00")
    )
    assert _verkaeufer_ids(e_invoice_service.cii_xml_bytes(dokument)) == [(None, "12/345/67890"), ("FC", "12/345/67890")]


def test_verkaeufer_mit_ust_idnr_bekommt_keine_zusaetzliche_kennung():
    dokument = e_invoice_service.baue_cii_dokument(
        _mandant(steuernummer="12/345/67890"), _rechnung(), _kunde(), [_position()], Decimal("300.00"), Decimal("357.00")
    )
    assert _verkaeufer_ids(e_invoice_service.cii_xml_bytes(dokument)) == [("VA", "DE123456789")]


_RAM_NS = {"ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"}


def _summen_und_korrekturen(xml: bytes) -> dict:
    from lxml import etree

    wurzel = etree.fromstring(xml)

    def text(pfad: str) -> list[str]:
        return [e.text for e in wurzel.xpath(pfad, namespaces=_RAM_NS)]

    kopf = "//ram:ApplicableHeaderTradeSettlement"
    return {
        "zeilen": text("//ram:IncludedSupplyChainTradeLineItem//ram:LineTotalAmount"),
        "zeilensumme": text(f"{kopf}//ram:LineTotalAmount"),
        "zuschlaege": text(f"{kopf}//ram:ChargeTotalAmount"),
        "abschlaege": text(f"{kopf}//ram:AllowanceTotalAmount"),
        "basis": text(f"{kopf}//ram:TaxBasisTotalAmount"),
        "korrekturen": [
            (
                e.xpath("string(ram:ChargeIndicator/*)", namespaces=_RAM_NS),
                e.xpath("string(ram:ActualAmount)", namespaces=_RAM_NS),
                e.xpath("string(ram:Reason)", namespaces=_RAM_NS),
                e.xpath("string(ram:CategoryTradeTax/ram:CategoryCode)", namespaces=_RAM_NS),
            )
            for e in wurzel.xpath(f"{kopf}/ram:SpecifiedTradeAllowanceCharge", namespaces=_RAM_NS)
        ],
    }


def test_rundungsdifferenz_abschlag_wenn_zeilen_hoeher_als_gruppensumme():
    # 2 x (0,5 x 10,01 = 5,005 -> 5,01) = 10,02, die Gruppe rundet erst die Rohsumme 10,01.
    positionen = [
        _position(position=1, menge=Decimal("0.5"), einzelpreis=Decimal("10.01")),
        _position(position=2, menge=Decimal("0.5"), einzelpreis=Decimal("10.01")),
    ]
    dokument = e_invoice_service.baue_cii_dokument(
        _mandant(), _rechnung(), _kunde(), positionen, Decimal("10.01"), Decimal("11.91")
    )
    ergebnis = _summen_und_korrekturen(e_invoice_service.cii_xml_bytes(dokument))
    assert ergebnis["zeilen"] == ["5.01", "5.01"]
    assert ergebnis["zeilensumme"] == ["10.02"]
    assert ergebnis["abschlaege"] == ["0.01"] and ergebnis["zuschlaege"] == ["0.00"]
    assert ergebnis["basis"] == ["10.01"]
    assert ergebnis["korrekturen"] == [("false", "0.01", "Rundungsdifferenz", "S")]


def test_rundungsdifferenz_zuschlag_wenn_zeilen_niedriger_als_gruppensumme():
    # 3 x (0,33 x 1,01 = 0,3333 -> 0,33) = 0,99, die Rohsumme 0,9999 rundet auf 1,00.
    positionen = [_position(position=i, menge=Decimal("0.33"), einzelpreis=Decimal("1.01")) for i in (1, 2, 3)]
    dokument = e_invoice_service.baue_cii_dokument(
        _mandant(), _rechnung(), _kunde(), positionen, Decimal("1.00"), Decimal("1.19")
    )
    ergebnis = _summen_und_korrekturen(e_invoice_service.cii_xml_bytes(dokument))
    assert ergebnis["zeilensumme"] == ["0.99"]
    assert ergebnis["zuschlaege"] == ["0.01"] and ergebnis["abschlaege"] == ["0.00"]
    assert ergebnis["korrekturen"] == [("true", "0.01", "Rundungsdifferenz", "S")]


def test_keine_rundungsdifferenz_wenn_zeilen_aufgehen():
    dokument = e_invoice_service.baue_cii_dokument(
        _mandant(), _rechnung(), _kunde(), [_position()], Decimal("300.00"), Decimal("357.00")
    )
    ergebnis = _summen_und_korrekturen(e_invoice_service.cii_xml_bytes(dokument))
    assert ergebnis["korrekturen"] == []
    assert ergebnis["zeilensumme"] == ergebnis["basis"] == ["300.00"]
