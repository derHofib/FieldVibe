"""Empfang von E-Rechnungen: Parser (rein), Hybrid-PDF, Sicherheit, Import,
Archivierung, Rechte/RLS, Mail-Import und Papierkorb."""
import hashlib
import io
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.db.session import system_session
from app.models.eingangsrechnung import Eingangsrechnung
from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.rechnung import Rechnung, RechnungPosition
from app.services import e_invoice_service, storage_service
from app.services import e_rechnung_empfang_service as empfang
from app.services.e_rechnung_empfang_service import ERechnungFehler, parse_e_rechnung
from tests.conftest import auth_headers, login


# --- Testdaten ----------------------------------------------------------------


def _mandant() -> Mandant:
    return Mandant(
        id=uuid4(),
        name="Elektro Mueller GmbH",
        slug="mueller",
        firmendaten={
            "adresse": {"strasse": "Musterstr. 1", "plz": "12345", "ort": "Musterstadt"},
            "ust_idnr": "DE123456789",
        },
    )


def _kunde() -> Kunde:
    return Kunde(
        id=uuid4(),
        kundennummer="K-1",
        name="Handwerk Beispiel GmbH",
        typ="gewerbe",
        ansprechpartner=[],
        adresse={"strasse": "Kundenweg 2", "plz": "54321", "ort": "Kundenstadt"},
        ust_idnr="DE987654321",
        portal_slug=uuid4().hex,
    )


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
        "faellig_am": date(2026, 9, 10),
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


def cii_bytes(rechnung=None, positionen=None, netto=Decimal("300.00"), brutto=Decimal("357.00")) -> bytes:
    dokument = e_invoice_service.baue_cii_dokument(
        _mandant(), rechnung or _rechnung(), _kunde(), positionen or [_position()], netto, brutto
    )
    return e_invoice_service.cii_xml_bytes(dokument)


def mischsteuer_cii() -> bytes:
    positionen = [
        _position(position=1, beschreibung="Kabel", einzelpreis=Decimal("100.00"),
                  steuer_kategorie="S", steuer_satz=Decimal("19.00")),
        _position(position=2, beschreibung="Fachbuch", einzelpreis=Decimal("50.00"),
                  steuer_kategorie="S", steuer_satz=Decimal("7.00")),
    ]
    return cii_bytes(
        _rechnung(betrag_netto=Decimal("150.00"), rechnungsnummer="R-MISCH"), positionen, Decimal("150.00"), Decimal("172.50")
    )


def ae_cii() -> bytes:
    positionen = [
        _position(einzelpreis=Decimal("1000.00"), steuer_kategorie="AE", steuer_satz=Decimal("0.00"),
                  steuer_grund="reverse_charge_13b")
    ]
    return cii_bytes(
        _rechnung(betrag_netto=Decimal("1000.00"), mwst_satz=Decimal("0.00"), rechnungsnummer="R-AE"), positionen,
        Decimal("1000.00"), Decimal("1000.00"),
    )


def ubl_bytes(
    *,
    wurzel="Invoice",
    nummer="UBL-2026-1",
    datum="2026-08-01",
    faellig="2026-08-31",
    waehrung="EUR",
    typ="380",
    name="Kabelwerk Nord GmbH",
    zeilen=None,
    netto="200.00",
    steuer="38.00",
    brutto="238.00",
    steuer_unterposten=None,
    extra="",
) -> bytes:
    """Minimale, handgeschriebene XRechnung-UBL (Invoice bzw. CreditNote)."""
    gutschrift = wurzel == "CreditNote"
    ns = f"urn:oasis:names:specification:ubl:schema:xsd:{wurzel}-2"
    zeilen = zeilen or [("1", "Verlegekabel NYM-J 3x1,5", "100", "MTR", "2.00", "200.00", "S", "19")]
    zeilen_xml = ""
    for nr, bez, menge, einheit, preis, summe, kat, satz in zeilen:
        tag = "CreditNoteLine" if gutschrift else "InvoiceLine"
        mtag = "CreditedQuantity" if gutschrift else "InvoicedQuantity"
        zeilen_xml += f"""
  <cac:{tag}>
    <cbc:ID>{nr}</cbc:ID>
    <cbc:{mtag} unitCode="{einheit}">{menge}</cbc:{mtag}>
    <cbc:LineExtensionAmount currencyID="{waehrung}">{summe}</cbc:LineExtensionAmount>
    <cac:Item>
      <cbc:Name>{bez}</cbc:Name>
      <cac:ClassifiedTaxCategory><cbc:ID>{kat}</cbc:ID><cbc:Percent>{satz}</cbc:Percent>
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:ClassifiedTaxCategory>
    </cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="{waehrung}">{preis}</cbc:PriceAmount></cac:Price>
  </cac:{tag}>"""
    unterposten = steuer_unterposten or [("S", "19", netto, steuer, "")]
    sub_xml = ""
    for kat, satz, basis, betrag, grund in unterposten:
        sub_xml += f"""
    <cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="{waehrung}">{basis}</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="{waehrung}">{betrag}</cbc:TaxAmount>
      <cac:TaxCategory><cbc:ID>{kat}</cbc:ID><cbc:Percent>{satz}</cbc:Percent>{grund}
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:TaxCategory>
    </cac:TaxSubtotal>"""
    nummer_xml = f"<cbc:ID>{nummer}</cbc:ID>" if nummer else ""
    datum_xml = f"<cbc:IssueDate>{datum}</cbc:IssueDate>" if datum else ""
    typ_tag = "CreditNoteTypeCode" if gutschrift else "InvoiceTypeCode"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<{wurzel} xmlns="{ns}"
    xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
    xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:CustomizationID>urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0</cbc:CustomizationID>
  {nummer_xml}
  {datum_xml}
  <cbc:DueDate>{faellig}</cbc:DueDate>
  <cbc:{typ_tag}>{typ}</cbc:{typ_tag}>
  <cbc:DocumentCurrencyCode>{waehrung}</cbc:DocumentCurrencyCode>
  <cac:AccountingSupplierParty><cac:Party>
    <cac:PartyName><cbc:Name>Kabelwerk</cbc:Name></cac:PartyName>
    <cac:PostalAddress><cbc:StreetName>Industrieweg 5</cbc:StreetName><cbc:CityName>Hamburg</cbc:CityName>
      <cbc:PostalZone>20095</cbc:PostalZone><cac:Country><cbc:IdentificationCode>DE</cbc:IdentificationCode></cac:Country>
    </cac:PostalAddress>
    <cac:PartyTaxScheme><cbc:CompanyID>DE811234567</cbc:CompanyID><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>
    <cac:PartyLegalEntity><cbc:RegistrationName>{name}</cbc:RegistrationName></cac:PartyLegalEntity>
    <cac:Contact><cbc:Name>Frau Vertrieb</cbc:Name><cbc:Telephone>040 123</cbc:Telephone><cbc:ElectronicMail>rechnung@kabelwerk.example</cbc:ElectronicMail></cac:Contact>
  </cac:Party></cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty><cac:Party><cac:PartyLegalEntity><cbc:RegistrationName>Elektro Mueller GmbH</cbc:RegistrationName></cac:PartyLegalEntity></cac:Party></cac:AccountingCustomerParty>
  <cac:PaymentMeans><cbc:PaymentMeansCode>58</cbc:PaymentMeansCode><cbc:PaymentID>{nummer}</cbc:PaymentID>
    <cac:PayeeFinancialAccount><cbc:ID>DE02120300000000202051</cbc:ID></cac:PayeeFinancialAccount></cac:PaymentMeans>
  <cac:PaymentTerms><cbc:Note>Zahlbar innerhalb 30 Tagen netto</cbc:Note></cac:PaymentTerms>
  <cac:TaxTotal><cbc:TaxAmount currencyID="{waehrung}">{steuer}</cbc:TaxAmount>{sub_xml}
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="{waehrung}">{netto}</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="{waehrung}">{netto}</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="{waehrung}">{brutto}</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="{waehrung}">{brutto}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>{zeilen_xml}
{extra}
</{wurzel}>""".encode()


def hybrid_pdf(xml: bytes | None = None, *, nummer="R-00001") -> bytes:
    from app.services import pdf_service

    rechnung = _rechnung(rechnungsnummer=nummer)
    pdf = pdf_service.generate_rechnung_pdf(_mandant(), rechnung, _kunde(), [_position()], pdfa_output_intent=True)
    if xml is None:
        xml = cii_bytes(rechnung)
    return e_invoice_service.baue_hybrid_pdf(pdf, xml)


# --- Parser: CII -------------------------------------------------------------


def test_cii_roundtrip_eigene_e_rechnung_wird_wieder_gelesen():
    r = parse_e_rechnung(cii_bytes())

    assert r.syntax == "cii"
    assert r.typ_code == "380" and not r.ist_gutschrift
    assert r.nummer == "R-00001"
    assert r.datum == date(2026, 8, 11)
    assert r.faellig_am == date(2026, 9, 10)
    assert r.waehrung == "EUR"
    assert r.lieferant.name == "Elektro Mueller GmbH"
    assert r.lieferant.ust_idnr == "DE123456789"
    assert r.lieferant.anschrift.strasse == "Musterstr. 1"
    assert r.lieferant.anschrift.plz == "12345"
    assert r.lieferant.anschrift.ort == "Musterstadt"
    assert (r.summe_netto, r.summe_steuer, r.summe_brutto, r.zahlbetrag) == (
        Decimal("300.00"), Decimal("57.00"), Decimal("357.00"), Decimal("357.00"),
    )
    assert r.zahlungsreferenz == "R-00001"
    assert len(r.positionen) == 1
    p = r.positionen[0]
    assert (p.name, p.menge, p.einheit, p.einzelpreis, p.netto) == (
        "Elektroinstallation", Decimal("1"), "Stk", Decimal("300.00"), Decimal("300.00"),
    )
    assert (p.steuer_kategorie, p.steuer_satz) == ("S", Decimal("19.00"))
    assert [(g.kategorie, g.satz, g.basis, g.steuer) for g in r.steuergruppen] == [
        ("S", Decimal("19.00"), Decimal("300.00"), Decimal("57.00"))
    ]


def test_cii_uebernahme_einfacher_fall_ohne_hinweis():
    u = empfang.baue_uebernahme(parse_e_rechnung(cii_bytes()))

    assert u.import_hinweis is None
    assert (u.betrag_netto, u.mwst_satz) == (Decimal("300.00"), Decimal("19.00"))
    assert [(p.beschreibung, p.menge, p.einzelpreis) for p in u.positionen] == [
        ("Elektroinstallation", Decimal("1"), Decimal("300.00"))
    ]
    assert "USt-IdNr. DE123456789" in u.notiz


def test_cii_gutschrift_wird_negativ_uebernommen():
    xml = cii_bytes(_rechnung(ist_storno=True))
    r = parse_e_rechnung(xml)
    # drafthorse kennzeichnet unser Storno als 384 (Korrektur), keine Gutschrift
    assert r.typ_code == "384" and not r.ist_gutschrift
    assert "Rechnungskorrektur" in empfang.baue_uebernahme(r).import_hinweis

    gutschrift = xml.replace(b"<ram:TypeCode>384</ram:TypeCode>", b"<ram:TypeCode>381</ram:TypeCode>", 1)
    r = parse_e_rechnung(gutschrift)
    assert r.ist_gutschrift
    assert (r.summe_netto, r.summe_brutto, r.zahlbetrag) == (Decimal("-300.00"), Decimal("-357.00"), Decimal("-357.00"))
    assert r.positionen[0].einzelpreis == Decimal("-300.00") and r.positionen[0].menge == Decimal("1")
    assert r.steuergruppen[0].steuer == Decimal("-57.00")
    u = empfang.baue_uebernahme(r)
    assert u.betrag_netto == Decimal("-300.00")
    assert u.import_hinweis == "Gutschrift (Typcode 381) – Beträge als negative Werte übernommen"


def test_cii_mischsteuer_waehlt_groessten_netto_anteil_und_warnt():
    r = parse_e_rechnung(mischsteuer_cii())
    assert {(g.kategorie, g.satz) for g in r.steuergruppen} == {("S", Decimal("19.00")), ("S", Decimal("7.00"))}

    u = empfang.baue_uebernahme(r)
    assert u.mwst_satz == Decimal("19.00")
    assert u.betrag_netto == Decimal("150.00")
    assert [(p.beschreibung, p.einzelpreis) for p in u.positionen] == [
        ("Kabel", Decimal("100.00")), ("Fachbuch", Decimal("50.00"))
    ]
    assert u.hinweise[0] == "Mehrere Steuersätze (19 %, 7 %) – Vorsteuer bitte prüfen"
    # 150 netto * 19 % = 178,50 in FieldVibe, laut Datei 172,50 -> Zahlbetrag-Hinweis
    assert any("178,50" in h and "172,50" in h for h in u.hinweise)


def test_cii_reverse_charge_setzt_hinweis():
    r = parse_e_rechnung(ae_cii())
    u = empfang.baue_uebernahme(r)

    assert u.mwst_satz == Decimal("0.00")
    assert len(u.hinweise) == 1
    assert "§ 13b UStG" in u.hinweise[0] and "Kategorie AE" in u.hinweise[0]
    assert "Steuerschuldnerschaft des Leistungsempfängers" in u.hinweise[0]


def test_cii_fremdwaehrung_wird_abgelehnt():
    xml = cii_bytes().replace(b"<ram:InvoiceCurrencyCode>EUR", b"<ram:InvoiceCurrencyCode>USD")
    with pytest.raises(ERechnungFehler) as exc:
        parse_e_rechnung(xml)
    assert exc.value.grund == "fremdwaehrung"
    assert "USD" in str(exc.value) and "EUR" in str(exc.value)


def test_cii_pflichtfelder_fehlen_liefern_liste():
    xml = cii_bytes()
    xml = xml.replace(b"<ram:ID>R-00001</ram:ID>", b"", 1)
    xml = xml.replace(b"<ram:Name>Elektro Mueller GmbH</ram:Name>", b"", 1)
    with pytest.raises(ERechnungFehler) as exc:
        parse_e_rechnung(xml)
    assert exc.value.grund == "ungueltig"
    assert exc.value.meldungen == [
        "Pflichtfeld fehlt: Rechnungsnummer (BT-1)",
        "Pflichtfeld fehlt: Name des Lieferanten (BT-27)",
    ]


def test_cii_summen_fehlen():
    xml = cii_bytes()
    for tag in (b"TaxBasisTotalAmount", b"GrandTotalAmount", b"LineTotalAmount"):
        import re

        xml = re.sub(rb"<ram:" + tag + rb"[^>]*>[^<]*</ram:" + tag + rb">", b"", xml)
    # LineTotalAmount steckt auch in den Positionen -> dort nicht entfernen
    with pytest.raises(ERechnungFehler) as exc:
        parse_e_rechnung(xml)
    assert "Pflichtfeld fehlt: Nettosumme (BT-109)" in exc.value.meldungen
    assert "Pflichtfeld fehlt: Bruttosumme (BT-112)" in exc.value.meldungen


def test_zeile_mit_mehr_nachkommastellen_wird_zur_pauschale():
    positionen = [_position(menge=Decimal("1000"), einheit="Stk", einzelpreis=Decimal("0.0345"))]
    xml = cii_bytes(
        _rechnung(betrag_netto=Decimal("34.50")), positionen, Decimal("34.50"), Decimal("41.06")
    )
    # Unser eigener Export rundet den Einzelpreis auf Cent; Fremdsysteme liefern mehr Stellen.
    assert b"<ram:ChargeAmount>0.03</ram:ChargeAmount>" in xml
    xml = xml.replace(b"<ram:ChargeAmount>0.03</ram:ChargeAmount>", b"<ram:ChargeAmount>0.0345</ram:ChargeAmount>")
    r = parse_e_rechnung(xml)
    u = empfang.baue_uebernahme(r)
    assert r.positionen[0].einzelpreis == Decimal("0.0345")
    assert u.positionen[0].menge == Decimal("1") and u.positionen[0].einheit == "psch"
    assert u.positionen[0].einzelpreis == Decimal("34.50")
    assert "1000 Stk × 0,0345 EUR" in u.positionen[0].beschreibung
    assert u.betrag_netto == Decimal("34.50")


def test_abweichende_summen_werden_im_hinweis_vermerkt_nicht_abgebrochen():
    xml = cii_bytes().replace(b">357.00<", b">360.00<")
    u = empfang.baue_uebernahme(parse_e_rechnung(xml))
    assert any("357,00" in h and "360,00" in h for h in u.hinweise)

    # Nettosumme der Datei weicht von den Positionen ab
    xml = cii_bytes().replace(b"<ram:TaxBasisTotalAmount>300.00", b"<ram:TaxBasisTotalAmount>310.00")
    u = empfang.baue_uebernahme(parse_e_rechnung(xml))
    assert any("Summe der Positionen (300,00 EUR)" in h and "310,00" in h for h in u.hinweise)


def test_cent_toleranz_erzeugt_keinen_hinweis():
    xml = cii_bytes().replace(b">357.00<", b">357.01<")
    assert empfang.baue_uebernahme(parse_e_rechnung(xml)).import_hinweis is None


# --- Parser: UBL --------------------------------------------------------------


def test_ubl_rechnung_wird_gelesen():
    r = parse_e_rechnung(ubl_bytes())

    assert r.syntax == "ubl"
    assert (r.typ_code, r.nummer, r.datum, r.faellig_am) == ("380", "UBL-2026-1", date(2026, 8, 1), date(2026, 8, 31))
    assert r.lieferant.name == "Kabelwerk Nord GmbH"
    assert r.lieferant.ust_idnr == "DE811234567"
    assert r.lieferant.anschrift.ort == "Hamburg" and r.lieferant.anschrift.land == "DE"
    assert r.lieferant.kontakt_email == "rechnung@kabelwerk.example"
    assert r.iban == "DE02120300000000202051"
    assert r.zahlungsreferenz == "UBL-2026-1"
    assert r.zahlungsbedingungen == "Zahlbar innerhalb 30 Tagen netto"
    assert (r.summe_netto, r.summe_steuer, r.summe_brutto) == (Decimal("200.00"), Decimal("38.00"), Decimal("238.00"))
    p = r.positionen[0]
    assert (p.name, p.menge, p.einheit, p.einzelpreis, p.netto) == (
        "Verlegekabel NYM-J 3x1,5", Decimal("100"), "m", Decimal("2.00"), Decimal("200.00"),
    )

    u = empfang.baue_uebernahme(r)
    assert u.import_hinweis is None
    assert "IBAN DE02120300000000202051" in u.notiz


def test_ubl_creditnote_wird_negativ_uebernommen():
    r = parse_e_rechnung(ubl_bytes(wurzel="CreditNote", typ="381", nummer="G-1"))

    assert r.ist_gutschrift and r.typ_code == "381"
    assert (r.summe_netto, r.summe_brutto) == (Decimal("-200.00"), Decimal("-238.00"))
    assert r.positionen[0].einzelpreis == Decimal("-2.00") and r.positionen[0].menge == Decimal("100")
    assert empfang.baue_uebernahme(r).betrag_netto == Decimal("-200.00")


def test_ubl_mischsteuer_und_reverse_charge():
    zeilen = [
        ("1", "Kabel", "1", "H87", "100.00", "100.00", "S", "19"),
        ("2", "Buch", "1", "H87", "50.00", "50.00", "S", "7"),
    ]
    unter = [("S", "19", "100.00", "19.00", ""), ("S", "7", "50.00", "3.50", "")]
    r = parse_e_rechnung(
        ubl_bytes(zeilen=zeilen, netto="150.00", steuer="22.50", brutto="172.50", steuer_unterposten=unter)
    )
    assert empfang.baue_uebernahme(r).hinweise[0] == "Mehrere Steuersätze (19 %, 7 %) – Vorsteuer bitte prüfen"

    zeilen_ae = [("1", "Bauleistung", "1", "H87", "500.00", "500.00", "AE", "0")]
    unter_ae = [("AE", "0", "500.00", "0.00", "<cbc:TaxExemptionReason>Reverse Charge</cbc:TaxExemptionReason>")]
    r = parse_e_rechnung(
        ubl_bytes(zeilen=zeilen_ae, netto="500.00", steuer="0.00", brutto="500.00", steuer_unterposten=unter_ae)
    )
    u = empfang.baue_uebernahme(r)
    assert u.mwst_satz == Decimal("0.00")
    assert "Kategorie AE" in u.hinweise[0] and "Grund laut Datei: Reverse Charge" in u.hinweise[0]


def test_ubl_fremdwaehrung_und_fehlende_pflichtfelder():
    with pytest.raises(ERechnungFehler) as exc:
        parse_e_rechnung(ubl_bytes(waehrung="CHF"))
    assert exc.value.grund == "fremdwaehrung"

    with pytest.raises(ERechnungFehler) as exc:
        parse_e_rechnung(ubl_bytes(nummer="", datum=""))
    assert exc.value.meldungen == [
        "Pflichtfeld fehlt: Rechnungsnummer (BT-1)",
        "Pflichtfeld fehlt: Rechnungsdatum (BT-2)",
    ]


def test_ungueltiger_zahlenwert_und_nan_werden_abgelehnt():
    with pytest.raises(ERechnungFehler, match="Ungültiger Zahlenwert"):
        parse_e_rechnung(ubl_bytes(brutto="NaN"))
    with pytest.raises(ERechnungFehler, match="Ungültiger Zahlenwert"):
        parse_e_rechnung(ubl_bytes(brutto="zwölf"))


def test_zu_grosser_betrag_wird_abgelehnt():
    r = parse_e_rechnung(ubl_bytes(netto="200000000.00", steuer="0.00", brutto="200000000.00",
                                   zeilen=[("1", "Zu teuer", "1", "H87", "200000000.00", "200000000.00", "S", "0")]))
    with pytest.raises(ERechnungFehler, match="darstellbaren Bereich"):
        empfang.baue_uebernahme(r)


# --- Syntaxerkennung, defekte Dateien -----------------------------------------


def test_falsche_wurzel_liefert_klare_meldung():
    with pytest.raises(ERechnungFehler, match="Unbekanntes Wurzelelement 'Bestellung'"):
        parse_e_rechnung(b'<?xml version="1.0"?><Bestellung><ID>1</ID></Bestellung>')
    # UBL-Namespace, aber kein Invoice/CreditNote
    with pytest.raises(ERechnungFehler, match="Unbekanntes Wurzelelement"):
        parse_e_rechnung(
            b'<Order xmlns="urn:oasis:names:specification:ubl:schema:xsd:Order-2"><ID>1</ID></Order>'
        )
    # ZUGFeRD 1.0 hat einen anderen Namespace
    with pytest.raises(ERechnungFehler, match="Unbekanntes Wurzelelement"):
        parse_e_rechnung(b'<rsm:CrossIndustryDocument xmlns:rsm="urn:ferd:CrossIndustryDocument:invoice:1p0"/>')


def test_defektes_xml():
    with pytest.raises(ERechnungFehler, match="kein wohlgeformtes XML"):
        parse_e_rechnung(b"<rsm:CrossIndustryInvoice><unclosed>")
    with pytest.raises(ERechnungFehler, match="kein wohlgeformtes XML"):
        parse_e_rechnung(b"")
    with pytest.raises(ERechnungFehler, match="kein wohlgeformtes XML"):
        parse_e_rechnung(b"\x00\x01\x02 kein xml")


def test_zu_grosse_xml_datei():
    gross = ubl_bytes(extra="<!-- " + "x" * empfang.XML_MAX_BYTES + " -->")
    with pytest.raises(ERechnungFehler) as exc:
        parse_e_rechnung(gross)
    assert exc.value.grund == "zu_gross"


# --- Sicherheit ----------------------------------------------------------------

_XXE = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE Invoice [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
    xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ID>&xxe;</cbc:ID>
</Invoice>"""


def _billion_laughs() -> bytes:
    ebenen = ['<!ENTITY lol0 "lol">']
    for i in range(1, 10):
        ebenen.append(f'<!ENTITY lol{i} "' + f"&lol{i - 1};" * 10 + '">')
    return (
        '<?xml version="1.0"?><!DOCTYPE Invoice [' + "".join(ebenen) + "]>"
        '<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" '
        'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">'
        "<cbc:ID>&lol9;</cbc:ID></Invoice>"
    ).encode()


def test_xxe_dokument_wird_abgelehnt_ohne_dateiinhalt(caplog):
    caplog.set_level(logging.DEBUG)
    with pytest.raises(ERechnungFehler) as exc:
        parse_e_rechnung(_XXE)
    assert "DOCTYPE" in str(exc.value)
    assert "root:" not in str(exc.value)
    assert "root:" not in caplog.text


def test_xxe_auch_als_cii_und_mit_externer_dtd():
    cii_mit_xxe = cii_bytes().replace(
        b"<rsm:CrossIndustryInvoice",
        b'<!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><rsm:CrossIndustryInvoice',
        1,
    )
    # Deklaration steht nach der XML-Deklaration
    cii_mit_xxe = cii_mit_xxe.replace(b"?><!DOCTYPE", b"?>\n<!DOCTYPE")
    with pytest.raises(ERechnungFehler, match="DOCTYPE"):
        parse_e_rechnung(cii_mit_xxe)
    extern = ubl_bytes().replace(
        b"<Invoice", b'<!DOCTYPE Invoice SYSTEM "http://127.0.0.1:1/boese.dtd"><Invoice', 1
    )
    with pytest.raises(ERechnungFehler, match="DOCTYPE"):
        parse_e_rechnung(extern)


def test_entity_expansion_wird_abgelehnt_und_ist_schnell():
    import time

    start = time.monotonic()
    # libxml2 bricht die Expansionsbombe teils selbst ab (dann "nicht wohlgeformt"), sonst greift die DTD-Sperre.
    with pytest.raises(ERechnungFehler, match="DOCTYPE|wohlgeformt"):
        parse_e_rechnung(_billion_laughs())
    assert time.monotonic() - start < 2


def test_parameter_entity_und_xinclude_werden_nicht_aufgeloest():
    xinclude = ubl_bytes(
        extra='<xi:include xmlns:xi="http://www.w3.org/2001/XInclude" parse="text" href="file:///etc/passwd"/>'
    )
    r = parse_e_rechnung(xinclude)
    assert "root:" not in repr(r)


# --- Hybrid-PDF ----------------------------------------------------------------


def test_hybrid_pdf_xml_wird_byte_identisch_ausgelesen():
    xml = cii_bytes(_rechnung(rechnungsnummer="R-HYB-1"))
    pdf = hybrid_pdf(xml, nummer="R-HYB-1")

    assert empfang.ist_pdf(pdf)
    ausgelesen = empfang.extrahiere_xml_aus_pdf(pdf)
    assert ausgelesen is not None
    assert parse_e_rechnung(ausgelesen).nummer == "R-HYB-1"
    # drafthorse haengt die XML unveraendert an
    assert hashlib.sha256(ausgelesen).hexdigest() == hashlib.sha256(xml).hexdigest()


def test_gewoehnliches_pdf_hat_keine_e_rechnung():
    from app.services import pdf_service

    pdf = pdf_service.generate_rechnung_pdf(_mandant(), _rechnung(), _kunde(), [_position()])
    assert empfang.extrahiere_xml_aus_pdf(pdf) is None
    assert empfang.extrahiere_xml_aus_pdf(b"%PDF-1.4 fake") is None


def test_pdf_zu_gross_und_anhangs_begrenzung():
    with pytest.raises(ERechnungFehler) as exc:
        empfang.extrahiere_xml_aus_pdf(b"%PDF-1.4" + b"0" * empfang.PDF_MAX_BYTES)
    assert exc.value.grund == "zu_gross"


def _pdf_mit_anhaengen(anhaenge: list[tuple[str, bytes]]) -> bytes:
    import io

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    for name, inhalt in anhaenge:
        writer.add_attachment(name, inhalt)
    puffer = io.BytesIO()
    writer.write(puffer)
    return puffer.getvalue()


def test_pdf_anhang_namen_gross_klein_und_prioritaet():
    pdf = _pdf_mit_anhaengen([("ZUGFeRD-invoice.xml", b"<b/>"), ("xrechnung.xml", b"<c/>"), ("notiz.txt", b"x")])
    assert empfang.extrahiere_xml_aus_pdf(pdf) == b"<b/>"
    pdf = _pdf_mit_anhaengen([("xrechnung.xml", b"<c/>"), ("factur-x.xml", b"<a/>")])
    assert empfang.extrahiere_xml_aus_pdf(pdf) == b"<a/>"
    assert empfang.extrahiere_xml_aus_pdf(_pdf_mit_anhaengen([("anderes.xml", b"<d/>")])) is None


def test_pdf_mit_zu_grossem_xml_anhang(monkeypatch):
    monkeypatch.setattr(empfang, "XML_MAX_BYTES", 1000)
    pdf = _pdf_mit_anhaengen([("factur-x.xml", b"<a>" + b"x" * 2000 + b"</a>")])
    with pytest.raises(ERechnungFehler) as exc:
        empfang.extrahiere_xml_aus_pdf(pdf)
    assert exc.value.grund == "zu_gross"


def test_pdf_anhangszahl_ist_begrenzt(monkeypatch):
    monkeypatch.setattr(empfang, "_ANHANG_MAX_ANZAHL", 3)
    anhaenge = [(f"datei{i}.txt", b"x") for i in range(5)] + [("factur-x.xml", b"<a/>")]
    assert empfang.extrahiere_xml_aus_pdf(_pdf_mit_anhaengen(anhaenge)) is None


# --- API: Import, Archivierung, Duplikate, Rechte ----------------------------------


async def _admin(client, make_mandant, make_user, mandant=None):
    mandant = mandant or await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    return mandant, auth_headers(token)


async def _hochladen(client, headers, daten: bytes, name="rechnung.xml", typ="application/xml"):
    return await client.post(
        "/api/eingangsrechnungen/e-rechnung", headers=headers, files={"file": (name, io.BytesIO(daten), typ)}
    )


async def _zeile(eingangsrechnung_id) -> Eingangsrechnung:
    async with system_session() as session:
        return await session.get(Eingangsrechnung, UUID(eingangsrechnung_id))


async def test_xml_upload_legt_eingangsrechnung_an_und_archiviert_original(client, make_mandant, make_user):
    _, headers = await _admin(client, make_mandant, make_user)
    xml = ubl_bytes()

    resp = await _hochladen(client, headers, xml)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "offen"
    assert body["lieferant_name"] == "Kabelwerk Nord GmbH" and body["lieferant_id"] is None
    assert body["rechnungsnummer_lieferant"] == "UBL-2026-1"
    assert body["rechnungsdatum"] == "2026-08-01" and body["faellig_am"] == "2026-08-31"
    assert body["eingegangen_am"] == date.today().isoformat()
    assert (body["betrag_netto"], body["mwst_satz"], body["betrag_brutto"]) == ("200.00", "19.00", "238.00")
    assert body["e_rechnung_syntax"] == "ubl" and body["hat_xml"] is True
    assert body["import_hinweis"] is None
    assert body["beleg_object_key"] is None
    assert len(body["positionen"]) == 1 and body["positionen"][0]["gesamt"] == "200.00"
    assert body["xml_sha256"] == hashlib.sha256(xml).hexdigest()

    zeile = await _zeile(body["id"])
    assert zeile.erstellt_von is not None
    assert await storage_service.download_bytes(zeile.xml_object_key) == xml

    url = (await client.get(f"/api/eingangsrechnungen/{body['id']}/xml-url", headers=headers)).json()["url"]
    assert zeile.xml_object_key in url


async def test_hybrid_pdf_upload_archiviert_pdf_und_xml_byte_identisch(client, make_mandant, make_user):
    _, headers = await _admin(client, make_mandant, make_user)
    xml = cii_bytes(_rechnung(rechnungsnummer="R-HYB-7"))
    pdf = hybrid_pdf(xml, nummer="R-HYB-7")

    resp = await _hochladen(client, headers, pdf, "rechnung.pdf", "application/pdf")

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["e_rechnung_syntax"] == "cii" and body["hat_xml"] and body["beleg_object_key"]
    zeile = await _zeile(body["id"])
    assert await storage_service.download_bytes(zeile.beleg_object_key) == pdf
    assert await storage_service.download_bytes(zeile.xml_object_key) == xml
    assert zeile.xml_sha256 == hashlib.sha256(xml).hexdigest() == body["xml_sha256"]


async def test_lieferant_wird_ueber_den_namen_zugeordnet(client, make_mandant, make_user):
    _, headers = await _admin(client, make_mandant, make_user)
    lieferant = (await client.post("/api/lieferanten", headers=headers, json={"name": "Kabelwerk  NORD GmbH"})).json()

    body = (await _hochladen(client, headers, ubl_bytes())).json()

    assert body["lieferant_id"] == lieferant["id"]
    assert body["lieferant_name"] == "Kabelwerk  NORD GmbH"


async def test_gutschrift_und_mischsteuer_ueber_die_api(client, make_mandant, make_user):
    _, headers = await _admin(client, make_mandant, make_user)

    gutschrift = (await _hochladen(client, headers, ubl_bytes(wurzel="CreditNote", typ="381", nummer="G-1"))).json()
    assert gutschrift["betrag_netto"] == "-200.00" and gutschrift["betrag_brutto"] == "-238.00"
    assert gutschrift["import_hinweis"] == "Gutschrift (Typcode 381) – Beträge als negative Werte übernommen"

    misch = (await _hochladen(client, headers, mischsteuer_cii(), "m.xml")).json()
    assert misch["mwst_satz"] == "19.00" and misch["betrag_netto"] == "150.00"
    assert misch["import_hinweis"].splitlines()[0] == "Mehrere Steuersätze (19 %, 7 %) – Vorsteuer bitte prüfen"
    assert [p["beschreibung"] for p in misch["positionen"]] == ["Kabel", "Fachbuch"]

    ae = (await _hochladen(client, headers, ae_cii(), "ae.xml")).json()
    assert ae["mwst_satz"] == "0.00" and "§ 13b UStG" in ae["import_hinweis"]


async def test_duplikat_wird_mit_409_abgelehnt(client, make_mandant, make_user):
    mandant, headers = await _admin(client, make_mandant, make_user)
    assert (await _hochladen(client, headers, ubl_bytes())).status_code == 201

    # identische Datei
    zweite = await _hochladen(client, headers, ubl_bytes())
    assert zweite.status_code == 409
    assert "UBL-2026-1" in zweite.json()["detail"] and "bereits" in zweite.json()["detail"]

    # gleiche Nummer und Lieferant, andere Datei (anderer Betrag)
    anders = ubl_bytes(netto="300.00", steuer="57.00", brutto="357.00",
                       zeilen=[("1", "Kabel", "1", "H87", "300.00", "300.00", "S", "19")])
    assert (await _hochladen(client, headers, anders)).status_code == 409

    # anderer Lieferant, gleiche Nummer -> kein Duplikat
    assert (await _hochladen(client, headers, ubl_bytes(name="Elektro Gross AG"))).status_code == 201

    # Papierkorb zaehlt nicht: nach dem Loeschen ist ein erneuter Import moeglich
    liste = (await client.get("/api/eingangsrechnungen", headers=headers)).json()
    erste = next(e for e in liste if e["lieferant_name"] == "Kabelwerk Nord GmbH")
    assert (await client.delete(f"/api/eingangsrechnungen/{erste['id']}", headers=headers)).status_code == 204
    assert (await _hochladen(client, headers, ubl_bytes())).status_code == 201


async def test_duplikat_gilt_nur_im_eigenen_mandanten(client, make_mandant, make_user):
    _, headers_a = await _admin(client, make_mandant, make_user)
    _, headers_b = await _admin(client, make_mandant, make_user)
    assert (await _hochladen(client, headers_a, ubl_bytes())).status_code == 201
    assert (await _hochladen(client, headers_b, ubl_bytes())).status_code == 201


async def test_fehlerfaelle_liefern_422_mit_lesbarer_meldung(client, make_mandant, make_user):
    _, headers = await _admin(client, make_mandant, make_user)

    falsche_wurzel = await _hochladen(client, headers, b"<Bestellung/>")
    assert falsche_wurzel.status_code == 422
    assert "Unbekanntes Wurzelelement" in falsche_wurzel.json()["detail"][0]["msg"]

    defekt = await _hochladen(client, headers, b"<a><b></a>")
    assert defekt.status_code == 422 and "wohlgeformt" in defekt.json()["detail"][0]["msg"]

    fremd = await _hochladen(client, headers, ubl_bytes(waehrung="USD"))
    assert fremd.status_code == 422 and "USD" in fremd.json()["detail"][0]["msg"]

    fehlt = await _hochladen(client, headers, ubl_bytes(nummer="", datum=""))
    assert fehlt.status_code == 422
    assert [d["msg"] for d in fehlt.json()["detail"]] == [
        "Pflichtfeld fehlt: Rechnungsnummer (BT-1)",
        "Pflichtfeld fehlt: Rechnungsdatum (BT-2)",
    ]

    ohne_xml = await _hochladen(client, headers, b"%PDF-1.4 fake", "x.pdf", "application/pdf")
    assert ohne_xml.status_code == 422 and "keine eingebettete E-Rechnung" in ohne_xml.json()["detail"][0]["msg"]

    liste = (await client.get("/api/eingangsrechnungen", headers=headers)).json()
    assert liste == []


async def test_xxe_ueber_die_api_leakt_nichts(client, make_mandant, make_user, caplog):
    caplog.set_level(logging.DEBUG)
    _, headers = await _admin(client, make_mandant, make_user)

    resp = await _hochladen(client, headers, _XXE)

    assert resp.status_code == 422
    assert "root:" not in resp.text and "root:" not in caplog.text
    assert (await client.get("/api/eingangsrechnungen", headers=headers)).json() == []


async def test_zu_grosse_dateien_werden_abgelehnt(client, make_mandant, make_user):
    _, headers = await _admin(client, make_mandant, make_user)

    xml_zu_gross = await _hochladen(client, headers, b"<a>" + b" " * (empfang.XML_MAX_BYTES + 1) + b"</a>")
    assert xml_zu_gross.status_code == 413

    pdf_zu_gross = await _hochladen(
        client, headers, b"%PDF-1.4" + b"0" * empfang.PDF_MAX_BYTES, "x.pdf", "application/pdf"
    )
    assert pdf_zu_gross.status_code == 413


async def test_xml_im_beleg_upload_verweist_auf_den_neuen_endpunkt(client, make_mandant, make_user):
    _, headers = await _admin(client, make_mandant, make_user)
    angelegt = (await _hochladen(client, headers, ubl_bytes())).json()

    resp = await client.post(
        f"/api/eingangsrechnungen/{angelegt['id']}/beleg",
        headers=headers,
        files={"file": ("rechnung.xml", io.BytesIO(ubl_bytes()), "text/xml")},
    )
    assert resp.status_code == 400
    assert "E-Rechnung importieren" in resp.json()["detail"]


async def test_rechte_ohne_abrechnung_erstellen_sind_403(client, make_mandant, make_user):
    mandant = await make_mandant()
    for rolle in ("techniker", "mitarbeiter"):
        user = await make_user(mandant=mandant, role=rolle, password="pw-123456")
        headers = auth_headers(await login(client, user.email, "pw-123456"))
        assert (await _hochladen(client, headers, ubl_bytes())).status_code == 403, rolle
    assert (await client.post("/api/eingangsrechnungen/e-rechnung", files={"file": ("a.xml", b"<a/>")})).status_code in (401, 403)


async def test_techniker_darf_xml_url_sehen_aber_nicht_importieren(client, make_mandant, make_user):
    mandant, admin_headers = await _admin(client, make_mandant, make_user)
    angelegt = (await _hochladen(client, admin_headers, ubl_bytes())).json()

    # techniker hat abrechnung.sehen, ist aber laut Router-Rollen (mandant_admin/custom) zugelassen
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    headers = auth_headers(await login(client, techniker.email, "pw-123456"))
    assert (await client.get(f"/api/eingangsrechnungen/{angelegt['id']}/xml-url", headers=headers)).status_code == 200

    mitarbeiter = await make_user(mandant=mandant, role="mitarbeiter", password="pw-123456")
    headers = auth_headers(await login(client, mitarbeiter.email, "pw-123456"))
    assert (await client.get(f"/api/eingangsrechnungen/{angelegt['id']}/xml-url", headers=headers)).status_code == 403


async def test_anderer_mandant_sieht_die_xml_nicht(client, make_mandant, make_user):
    _, headers_a = await _admin(client, make_mandant, make_user)
    _, headers_b = await _admin(client, make_mandant, make_user)
    angelegt = (await _hochladen(client, headers_a, ubl_bytes())).json()

    assert (await client.get(f"/api/eingangsrechnungen/{angelegt['id']}/xml-url", headers=headers_b)).status_code == 404
    assert (await client.get(f"/api/eingangsrechnungen/{angelegt['id']}", headers=headers_b)).status_code == 404
    assert (await client.get("/api/eingangsrechnungen", headers=headers_b)).json() == []


async def test_xml_url_ohne_xml_ist_null(client, make_mandant, make_user):
    _, headers = await _admin(client, make_mandant, make_user)
    manuell = (
        await client.post(
            "/api/eingangsrechnungen",
            headers=headers,
            json={"lieferant_name": "X", "rechnungsnummer_lieferant": "1", "rechnungsdatum": "2026-01-01"},
        )
    ).json()
    assert manuell["hat_xml"] is False and manuell["e_rechnung_syntax"] is None
    assert (await client.get(f"/api/eingangsrechnungen/{manuell['id']}/xml-url", headers=headers)).json() == {"url": None}


async def test_papierkorb_behaelt_die_xml_und_purge_bleibt_gesperrt(client, make_mandant, make_user):
    # Der Papierkorb loescht nirgends S3-Objekte (auch nicht beleg_object_key); eine
    # importierte E-Rechnung ist 'offen', damit GoBD-gesperrt und nie endgueltig loeschbar.
    mandant, headers = await _admin(client, make_mandant, make_user)
    xml = ubl_bytes()
    angelegt = (await _hochladen(client, headers, xml)).json()
    zeile = await _zeile(angelegt["id"])

    assert (await client.delete(f"/api/eingangsrechnungen/{angelegt['id']}", headers=headers)).status_code == 204
    operativ = await make_user(mandant=mandant, role="loesch_operativ", password="pw-123456")
    op_headers = auth_headers(await login(client, operativ.email, "pw-123456"))
    purge = await client.delete(f"/api/papierkorb/eingangsrechnung/{angelegt['id']}", headers=op_headers)

    assert purge.status_code == 409 and "Aufbewahrungspflicht" in purge.json()["detail"]
    assert await storage_service.download_bytes(zeile.xml_object_key) == xml
    # soft-geloescht: kein Download mehr ueber die Route
    assert (await client.get(f"/api/eingangsrechnungen/{angelegt['id']}/xml-url", headers=headers)).status_code == 404

    restore = await client.post(f"/api/papierkorb/eingangsrechnung/{angelegt['id']}/wiederherstellen", headers=op_headers)
    assert restore.status_code == 204
    assert (await client.get(f"/api/eingangsrechnungen/{angelegt['id']}/xml-url", headers=headers)).json()["url"]


# --- Mail-Import ----------------------------------------------------------------------


def _mail(*, betreff="Ihre Rechnung", absender="Kabelwerk <buchhaltung@kabelwerk.example>", anhaenge=(), message_id=None):
    from email.message import EmailMessage

    nachricht = EmailMessage()
    nachricht["From"] = absender
    nachricht["To"] = "rechnung@mandant.de"
    nachricht["Subject"] = betreff
    if message_id:
        nachricht["Message-ID"] = message_id
    nachricht.set_content("Siehe Anhang.")
    for name, daten, haupt, unter in anhaenge:
        nachricht.add_attachment(daten, maintype=haupt, subtype=unter, filename=name)
    return bytes(nachricht)


async def _integration(mandant, monkeypatch, nachrichten, uid=7):
    from app.core.security import encrypt_secret
    from app.models.integration import MandantIntegration
    from app.services import email_ingest_service

    async with system_session() as session:
        session.add(
            MandantIntegration(
                mandant_id=mandant.id,
                typ="imap",
                config={"host": "imap.example.de", "port": 993, "user": "r@example.de", "mailbox": "INBOX"},
                secret_ref=encrypt_secret("pw"),
                aktiv=True,
            )
        )
    monkeypatch.setattr(email_ingest_service, "_fetch_neue_nachrichten", lambda _i: (nachrichten, uid))
    return email_ingest_service


async def _eingangsrechnungen(mandant) -> list[Eingangsrechnung]:
    from sqlalchemy import select

    async with system_session() as session:
        return list(
            (await session.execute(select(Eingangsrechnung).where(Eingangsrechnung.mandant_id == mandant.id)))
            .scalars()
            .all()
        )


async def _notifications(mandant) -> list[str]:
    from sqlalchemy import select

    from app.models.notification import Notification

    async with system_session() as session:
        rows = (await session.execute(select(Notification).where(Notification.mandant_id == mandant.id))).scalars().all()
        return [n.titel for n in rows]


async def test_mail_import_xml_anhang_wird_zur_offenen_eingangsrechnung(make_mandant, make_user, monkeypatch):
    mandant = await make_mandant()
    await make_user(mandant=mandant, role="mandant_admin")
    xml = ubl_bytes()
    service = await _integration(
        mandant, monkeypatch, [_mail(anhaenge=[("re.xml", xml, "application", "xml")])]
    )

    ergebnis = await service.run_email_ingest([mandant.id])

    assert ergebnis["neue_e_rechnungen"] == 1 and ergebnis["neue_entwuerfe"] == 0
    assert ergebnis["uebersprungen"] == {}
    (zeile,) = await _eingangsrechnungen(mandant)
    assert zeile.status == "offen" and zeile.erstellt_von is None
    assert zeile.rechnungsnummer_lieferant == "UBL-2026-1" and zeile.e_rechnung_syntax == "ubl"
    assert zeile.email_absender == "buchhaltung@kabelwerk.example" and zeile.email_betreff == "Ihre Rechnung"
    assert await storage_service.download_bytes(zeile.xml_object_key) == xml
    assert await _notifications(mandant) == ["Neue E-Rechnung per E-Mail: Kabelwerk Nord GmbH"]


async def test_mail_import_hybrid_pdf_wird_e_rechnung_und_gewoehnliches_pdf_bleibt_entwurf(
    make_mandant, make_user, monkeypatch
):
    mandant = await make_mandant()
    await make_user(mandant=mandant, role="mandant_admin")
    hybrid = hybrid_pdf(nummer="R-MAIL-1")
    service = await _integration(
        mandant,
        monkeypatch,
        [
            _mail(anhaenge=[("hybrid.pdf", hybrid, "application", "pdf")]),
            _mail(betreff="Ohne XML", anhaenge=[("normal.pdf", b"%PDF-1.4 fake", "application", "pdf")]),
        ],
    )

    ergebnis = await service.run_email_ingest([mandant.id])

    assert (ergebnis["neue_e_rechnungen"], ergebnis["neue_entwuerfe"]) == (1, 1)
    zeilen = {z.status: z for z in await _eingangsrechnungen(mandant)}
    assert zeilen["offen"].rechnungsnummer_lieferant == "R-MAIL-1" and zeilen["offen"].beleg_object_key
    assert await storage_service.download_bytes(zeilen["offen"].beleg_object_key) == hybrid
    assert zeilen["entwurf"].xml_object_key is None


async def test_mail_ohne_anhang_ist_nicht_still_sondern_benachrichtigung(make_mandant, make_user, monkeypatch):
    mandant = await make_mandant()
    await make_user(mandant=mandant, role="mandant_admin")
    service = await _integration(
        mandant,
        monkeypatch,
        [
            _mail(betreff="Newsletter", message_id="<n1@x>"),
            _mail(betreff="Bild", message_id="<n2@x>", anhaenge=[("logo.png", b"\x89PNG", "image", "png")]),
        ],
    )

    ergebnis = await service.run_email_ingest([mandant.id])

    assert ergebnis["neue_e_rechnungen"] == 0 and ergebnis["neue_entwuerfe"] == 0
    assert ergebnis["uebersprungen"] == {"kein_anhang": 1, "kein_verwertbarer_anhang": 1}
    assert {d["grund"]: d["betreff"] for d in ergebnis["uebersprungen_details"]} == {
        "kein_anhang": "Newsletter",
        "kein_verwertbarer_anhang": "Bild",
    }
    titel = await _notifications(mandant)
    assert len(titel) == 2 and all(t.startswith("E-Mail ohne Rechnungsanhang") for t in titel)


async def test_mail_import_fehlerhafte_xml_wird_gemeldet_nicht_stillschweigend(make_mandant, make_user, monkeypatch):
    mandant = await make_mandant()
    await make_user(mandant=mandant, role="mandant_admin")
    service = await _integration(
        mandant,
        monkeypatch,
        [
            _mail(anhaenge=[("kaputt.xml", b"<a><b></a>", "application", "xml")], message_id="<k@x>"),
            _mail(anhaenge=[("usd.xml", ubl_bytes(waehrung="USD"), "application", "xml")], message_id="<u@x>"),
            _mail(anhaenge=[("xxe.xml", _XXE, "application", "xml")], message_id="<x@x>"),
        ],
    )

    ergebnis = await service.run_email_ingest([mandant.id])

    assert ergebnis["neue_e_rechnungen"] == 0
    assert ergebnis["uebersprungen"] == {"ungueltig": 2, "fremdwaehrung": 1}
    assert await _eingangsrechnungen(mandant) == []
    titel = await _notifications(mandant)
    assert len(titel) == 3
    assert any("kaputt.xml" in t and "wohlgeformt" in t for t in titel)
    assert any("usd.xml" in t and "USD" in t for t in titel)
    assert not any("root:" in t for t in titel)


async def test_mail_import_defekte_xml_im_hybrid_pdf_behaelt_das_pdf_als_entwurf(make_mandant, make_user, monkeypatch):
    mandant = await make_mandant()
    await make_user(mandant=mandant, role="mandant_admin")
    kaputt = hybrid_pdf(cii_bytes().replace(b"CrossIndustryInvoice", b"Unsinn"), nummer="R-X")
    service = await _integration(mandant, monkeypatch, [_mail(anhaenge=[("h.pdf", kaputt, "application", "pdf")])])

    ergebnis = await service.run_email_ingest([mandant.id])

    assert ergebnis["neue_entwuerfe"] == 1 and ergebnis["neue_e_rechnungen"] == 0
    assert ergebnis["uebersprungen"] == {"ungueltig": 1}
    (zeile,) = await _eingangsrechnungen(mandant)
    assert zeile.status == "entwurf" and zeile.beleg_object_key
    assert "Eingebettete E-Rechnung nicht verwertbar" in zeile.import_hinweis


async def test_mail_import_duplikat_wird_uebersprungen_und_im_ergebnis_vermerkt(make_mandant, make_user, monkeypatch):
    mandant = await make_mandant()
    await make_user(mandant=mandant, role="mandant_admin")
    xml = ubl_bytes()
    anhang = ("re.xml", xml, "application", "xml")
    service = await _integration(
        mandant,
        monkeypatch,
        [_mail(anhaenge=[anhang], message_id="<d1@x>"), _mail(anhaenge=[anhang], message_id="<d2@x>")],
    )

    ergebnis = await service.run_email_ingest([mandant.id])

    assert ergebnis["neue_e_rechnungen"] == 1
    assert ergebnis["uebersprungen"] == {"duplikat": 1}
    (detail,) = ergebnis["uebersprungen_details"]
    assert detail["anhang"] == "re.xml" and "bereits" in detail["meldung"]
    assert len(await _eingangsrechnungen(mandant)) == 1
    # Duplikate erzeugen keine zusaetzliche Benachrichtigung
    assert len(await _notifications(mandant)) == 1


async def test_mail_import_meldet_denselben_fehler_nicht_bei_jedem_lauf_erneut(make_mandant, make_user, monkeypatch):
    mandant = await make_mandant()
    await make_user(mandant=mandant, role="mandant_admin")
    mail = _mail(message_id="<wieder@x>")
    service = await _integration(mandant, monkeypatch, [mail])

    await service.run_email_ingest([mandant.id])
    await service.run_email_ingest([mandant.id])

    assert len(await _notifications(mandant)) == 1


async def test_mail_import_begrenzt_einzelmeldungen_je_lauf(make_mandant, make_user, monkeypatch):
    mandant = await make_mandant()
    await make_user(mandant=mandant, role="mandant_admin")
    mails = [_mail(betreff=f"Spam {i}", message_id=f"<s{i}@x>") for i in range(14)]
    service = await _integration(mandant, monkeypatch, mails)

    ergebnis = await service.run_email_ingest([mandant.id])

    assert ergebnis["uebersprungen"] == {"kein_anhang": 14}
    titel = await _notifications(mandant)
    assert len(titel) == 11
    assert any("4 weitere Mail(s)" in t for t in titel)


async def test_mail_import_isoliert_mandanten(make_mandant, make_user, monkeypatch):
    mandant_a = await make_mandant()
    mandant_b = await make_mandant()
    await make_user(mandant=mandant_a, role="mandant_admin")
    await make_user(mandant=mandant_b, role="mandant_admin")
    xml = ubl_bytes()
    service = await _integration(mandant_a, monkeypatch, [_mail(anhaenge=[("a.xml", xml, "application", "xml")])])
    await service.run_email_ingest([mandant_a.id])
    service = await _integration(mandant_b, monkeypatch, [_mail(anhaenge=[("a.xml", xml, "application", "xml")])])
    # Zweite Integration von A bleibt aktiv; der Fetch liefert fuer beide dieselbe Mail -- B darf nicht als Duplikat gelten
    ergebnis = await service.run_email_ingest([mandant_b.id])

    assert ergebnis["neue_e_rechnungen"] == 1
    assert len(await _eingangsrechnungen(mandant_b)) == 1


# --- Migration -------------------------------------------------------------------------


def _alembic_cfg():
    import os

    from alembic.config import Config

    backend = os.path.dirname(os.path.dirname(__file__))
    cfg = Config(os.path.join(backend, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(backend, "alembic"))
    return cfg


async def _migrieren(richtung: str, ziel: str) -> None:
    import asyncio

    from alembic import command

    await asyncio.to_thread(getattr(command, richtung), _alembic_cfg(), ziel)


async def test_migration_0106_up_down_up():
    import os

    from sqlalchemy import create_engine, inspect

    from app.core.config import get_settings

    engine = create_engine(os.environ.get("DATABASE_URL_SYNC") or get_settings().database_url_sync)
    neu = {"xml_object_key", "xml_sha256", "e_rechnung_syntax", "import_hinweis"}
    checks = {"ck_eingangsrechnungen_e_rechnung_syntax_valid", "ck_eingangsrechnungen_xml_sha256_format"}
    try:
        await _migrieren("downgrade", "0105")
        assert neu.isdisjoint({c["name"] for c in inspect(engine).get_columns("eingangsrechnungen")})
        assert not checks & {c["name"] for c in inspect(engine).get_check_constraints("eingangsrechnungen")}

        await _migrieren("upgrade", "head")
        spalten = {c["name"]: c for c in inspect(engine).get_columns("eingangsrechnungen")}
        assert neu <= set(spalten) and all(spalten[n]["nullable"] for n in neu)
        assert checks <= {c["name"] for c in inspect(engine).get_check_constraints("eingangsrechnungen")}
    finally:
        await _migrieren("upgrade", "head")
        engine.dispose()


async def test_check_constraints_verhindern_ungueltige_werte(make_mandant):
    from sqlalchemy.exc import IntegrityError

    mandant = await make_mandant()
    for feld, wert in (("e_rechnung_syntax", "edifact"), ("xml_sha256", "ABC")):
        with pytest.raises(IntegrityError):
            async with system_session() as session:
                session.add(
                    Eingangsrechnung(
                        mandant_id=mandant.id,
                        lieferant_name="X",
                        rechnungsnummer_lieferant="1",
                        rechnungsdatum=date.today(),
                        **{feld: wert},
                    )
                )
