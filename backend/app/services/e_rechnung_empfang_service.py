"""Empfang von E-Rechnungen (XRechnung CII/UBL, ZUGFeRD/Factur-X) im
Rechnungseingang.

Die Eingabe ist nicht vertrauenswuerdig (Upload oder fremde E-Mail): XML wird
nur mit einem gehaerteten lxml-Parser gelesen und jedes DOCTYPE/DTD abgelehnt
(XXE, Entity-Expansion). Das Original-XML ist der Beleg im Sinne der GoBD/des
BMF-Schreibens vom 14.07.2025 -- es wird hier nie veraendert oder neu erzeugt,
sondern byte-identisch archiviert (siehe importiere_e_rechnung).

parse_e_rechnung() ist eine reine Funktion ohne DB/S3-Zugriff; der DB-nahe
Teil (Lieferantenzuordnung, Duplikate, Archivierung) steht weiter unten.
"""
import hashlib
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID

from lxml import etree
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.eingangsrechnung import Eingangsrechnung, EingangsrechnungPosition
from app.models.lieferant import Lieferant
from app.services import storage_service

logger = logging.getLogger(__name__)

XML_MAX_BYTES = 5 * 1024 * 1024
PDF_MAX_BYTES = 10 * 1024 * 1024
# Hybrid-PDFs tragen eine Handvoll Anhaenge; alles darueber ist ein
# Missbrauchsversuch (jeder Eintrag kostet beim Auslesen Speicher/CPU).
_ANHANG_MAX_ANZAHL = 50
_POSITIONEN_MAX = 2000

# Reihenfolge = Prioritaet, falls ein PDF mehrere passende Anhaenge hat.
E_RECHNUNG_ANHANGNAMEN = ("factur-x.xml", "zugferd-invoice.xml", "xrechnung.xml")

_NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
}
_UBL_WURZELN = {
    ("urn:oasis:names:specification:ubl:schema:xsd:Invoice-2", "Invoice"),
    ("urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2", "CreditNote"),
}

# UNTDID 1001: Gutschriften/Gutschriftsanzeigen. 380/384/389 sind Rechnungen
# (Korrektur bzw. Gutschriftsverfahren sind keine Vorzeichenumkehr).
_GUTSCHRIFT_TYPCODES = {"81", "83", "261", "381", "396", "532"}

_EINHEITEN = {
    "H87": "Stk", "C62": "Stk", "XPP": "Stk", "EA": "Stk", "HUR": "h", "MIN": "min", "DAY": "Tag",
    "MTR": "m", "KMT": "km", "MTK": "m²", "MTQ": "m³", "KGM": "kg", "GRM": "g", "TNE": "t",
    "LTR": "l", "SET": "Satz", "PR": "Paar", "LS": "psch", "MON": "Monat", "WEE": "Woche", "ANN": "Jahr",
}

_STEUERKATEGORIE_HINWEIS = {
    "AE": "Steuerschuldnerschaft des Leistungsempfängers (Reverse Charge, § 13b UStG, Kategorie AE) – "
    "keine Vorsteuer aus dieser Rechnung, Umsatz- und Vorsteuer bitte selbst erfassen",
    "Z": "Steuersatz 0 % (Kategorie Z) – Vorsteuer bitte prüfen",
    "E": "Steuerfreie Leistung (Kategorie E) – Vorsteuer bitte prüfen",
    "K": "Innergemeinschaftliche Lieferung (Kategorie K) – Erwerbsbesteuerung bitte prüfen",
    "G": "Ausfuhrlieferung (Kategorie G) – Vorsteuer bitte prüfen",
    "O": "Nicht steuerbar (Kategorie O) – Vorsteuer bitte prüfen",
}

_CENT = Decimal("0.01")
_SCHWELLE = Decimal("0.01")
_DB_BETRAG_GRENZE = Decimal("100000000")  # Numeric(10, 2)


class ERechnungFehler(Exception):
    """Eine E-Rechnung ist nicht verwertbar. grund steuert die Auswertung im
    E-Mail-Import (Zaehler je Grund) und den HTTP-Status der Route (immer 422,
    ausser zu_gross)."""

    def __init__(self, meldungen: str | list[str], grund: str = "ungueltig"):
        self.meldungen = [meldungen] if isinstance(meldungen, str) else list(meldungen)
        self.grund = grund
        super().__init__("; ".join(self.meldungen))


class ERechnungDuplikat(Exception):
    def __init__(self, eingangsrechnung_id, rechnungsnummer: str, lieferant_name: str):
        self.eingangsrechnung_id = eingangsrechnung_id
        self.rechnungsnummer = rechnungsnummer
        self.lieferant_name = lieferant_name
        super().__init__(
            f"Rechnung {rechnungsnummer} von {lieferant_name} ist bereits im Rechnungseingang vorhanden"
        )


@dataclass
class Anschrift:
    strasse: str | None = None
    plz: str | None = None
    ort: str | None = None
    land: str | None = None


@dataclass
class Lieferantendaten:
    name: str | None = None
    ust_idnr: str | None = None
    steuernummer: str | None = None
    anschrift: Anschrift = field(default_factory=Anschrift)
    kontakt_name: str | None = None
    kontakt_telefon: str | None = None
    kontakt_email: str | None = None


@dataclass
class Position:
    nummer: str | None
    name: str
    beschreibung: str | None
    menge: Decimal
    einheit: str
    einzelpreis: Decimal
    netto: Decimal
    steuer_kategorie: str | None
    steuer_satz: Decimal | None


@dataclass
class Steuergruppe:
    kategorie: str
    satz: Decimal
    basis: Decimal
    steuer: Decimal
    befreiungsgrund: str | None = None


@dataclass
class EmpfangeneRechnung:
    syntax: Literal["cii", "ubl"]
    typ_code: str
    ist_gutschrift: bool
    nummer: str
    datum: date
    faellig_am: date | None
    waehrung: str
    lieferant: Lieferantendaten
    positionen: list[Position]
    steuergruppen: list[Steuergruppe]
    steuergruppen_abgeleitet: bool
    summe_netto: Decimal
    summe_steuer: Decimal
    summe_brutto: Decimal
    zahlbetrag: Decimal
    vorausgezahlt: Decimal
    iban: str | None
    zahlungsreferenz: str | None
    zahlungsbedingungen: str | None


@dataclass
class PositionUebernahme:
    beschreibung: str
    menge: Decimal
    einheit: str
    einzelpreis: Decimal


@dataclass
class Uebernahme:
    """Das, was aus einer EmpfangeneRechnung in die Eingangsrechnung fliesst."""

    lieferant_name: str
    rechnungsnummer: str
    rechnungsdatum: date
    faellig_am: date | None
    betrag_netto: Decimal
    mwst_satz: Decimal
    positionen: list[PositionUebernahme]
    hinweise: list[str]
    notiz: str | None

    @property
    def import_hinweis(self) -> str | None:
        return "\n".join(self.hinweise) if self.hinweise else None


# --- Lesen/Parsen -----------------------------------------------------------


def _kurz(text: str, maximal: int = 60) -> str:
    # Fremde Strings landen in Fehlermeldungen: Steuerzeichen raus, Laenge kappen.
    bereinigt = re.sub(r"[^\w .:\-/]", "?", text)
    return bereinigt[:maximal]


def _lese_xml(xml_bytes: bytes) -> etree._Element:
    if len(xml_bytes) > XML_MAX_BYTES:
        raise ERechnungFehler("Die XML-Datei ist zu groß (max. 5 MB).", grund="zu_gross")
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        attribute_defaults=False,
        huge_tree=False,
        remove_comments=True,
        remove_pis=True,
        recover=False,
    )
    try:
        baum_root = etree.fromstring(xml_bytes, parser)
    except etree.XMLSyntaxError as exc:
        # Bewusst nicht exc.msg: libxml2 zitiert dort gelegentlich Dateiinhalt.
        raise ERechnungFehler(f"Die Datei ist kein wohlgeformtes XML (Zeile {exc.lineno}).") from None
    except (ValueError, etree.LxmlError):
        raise ERechnungFehler("Die Datei ist kein wohlgeformtes XML.") from None

    docinfo = baum_root.getroottree().docinfo
    if docinfo.doctype or docinfo.internalDTD is not None or docinfo.externalDTD is not None:
        raise ERechnungFehler(
            "Die Datei enthält eine DOCTYPE-/DTD-Deklaration und wird aus Sicherheitsgründen nicht verarbeitet. "
            "E-Rechnungen enthalten keine DTD."
        )
    return baum_root


def _text(knoten: etree._Element | None, pfad: str) -> str | None:
    if knoten is None:
        return None
    wert = knoten.findtext(pfad, namespaces=_NS)
    if wert is None:
        return None
    wert = wert.strip()
    return wert or None


def _dec(wert: str | None, bezeichnung: str) -> Decimal | None:
    if wert is None:
        return None
    try:
        zahl = Decimal(wert.strip())
    except InvalidOperation:
        raise ERechnungFehler(f"Ungültiger Zahlenwert bei {bezeichnung}.") from None
    if not zahl.is_finite():
        raise ERechnungFehler(f"Ungültiger Zahlenwert bei {bezeichnung}.")
    return zahl


def _dec_text(knoten: etree._Element | None, pfad: str, bezeichnung: str) -> Decimal | None:
    return _dec(_text(knoten, pfad), bezeichnung)


def _datum(wert: str | None, bezeichnung: str, format_code: str | None = None) -> date | None:
    if wert is None:
        return None
    wert = wert.strip()
    try:
        if format_code == "102" or re.fullmatch(r"\d{8}", wert):
            return datetime.strptime(wert[:8], "%Y%m%d").date()
        if re.match(r"\d{4}-\d{2}-\d{2}", wert):
            return date.fromisoformat(wert[:10])
    except ValueError:
        pass
    raise ERechnungFehler(f"Ungültiges Datum bei {bezeichnung}.")


def _cii_datum(knoten: etree._Element | None, pfad: str, bezeichnung: str) -> date | None:
    if knoten is None:
        return None
    el = knoten.find(pfad, namespaces=_NS)
    if el is None or el.text is None or not el.text.strip():
        return None
    return _datum(el.text, bezeichnung, el.get("format"))


def _einheit(code: str | None) -> str:
    if not code:
        return "Stk"
    return _EINHEITEN.get(code.strip().upper(), _kurz(code.strip(), 10))


def _bool(wert: str | None) -> bool:
    return (wert or "").strip().lower() in ("true", "1")


def _parse_cii(root: etree._Element) -> dict:
    dokument = root.find("rsm:ExchangedDocument", _NS)
    handel = root.find("rsm:SupplyChainTradeTransaction", _NS)
    vertrag = handel.find("ram:ApplicableHeaderTradeAgreement", _NS) if handel is not None else None
    abrechnung = handel.find("ram:ApplicableHeaderTradeSettlement", _NS) if handel is not None else None
    verkaeufer = vertrag.find("ram:SellerTradeParty", _NS) if vertrag is not None else None

    lieferant = Lieferantendaten(name=_text(verkaeufer, "ram:Name"))
    if verkaeufer is not None:
        for reg in verkaeufer.findall("ram:SpecifiedTaxRegistration/ram:ID", _NS):
            wert = (reg.text or "").strip()
            if not wert:
                continue
            if reg.get("schemeID") == "VA" and lieferant.ust_idnr is None:
                lieferant.ust_idnr = wert
            elif reg.get("schemeID") == "FC" and lieferant.steuernummer is None:
                lieferant.steuernummer = wert
        adresse = verkaeufer.find("ram:PostalTradeAddress", _NS)
        zeilen = [z for z in (_text(adresse, "ram:LineOne"), _text(adresse, "ram:LineTwo")) if z]
        lieferant.anschrift = Anschrift(
            strasse=", ".join(zeilen) or None,
            plz=_text(adresse, "ram:PostcodeCode"),
            ort=_text(adresse, "ram:CityName"),
            land=_text(adresse, "ram:CountryID"),
        )
        kontakt = verkaeufer.find("ram:DefinedTradeContact", _NS)
        lieferant.kontakt_name = _text(kontakt, "ram:PersonName") or _text(kontakt, "ram:DepartmentName")
        lieferant.kontakt_telefon = _text(kontakt, "ram:TelephoneUniversalCommunication/ram:CompleteNumber")
        lieferant.kontakt_email = _text(kontakt, "ram:EmailURIUniversalCommunication/ram:URIID")

    positionen: list[Position] = []
    if handel is not None:
        for zeile in handel.findall("ram:IncludedSupplyChainTradeLineItem", _NS):
            if len(positionen) >= _POSITIONEN_MAX:
                raise ERechnungFehler(f"Die Rechnung hat mehr als {_POSITIONEN_MAX} Positionen.")
            preis = _dec_text(zeile, "ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:ChargeAmount", "Nettopreis (BT-146)")
            preis_basis = _dec_text(zeile, "ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:BasisQuantity", "Preiseinheit (BT-149)")
            menge_el = zeile.find("ram:SpecifiedLineTradeDelivery/ram:BilledQuantity", _NS)
            menge = _dec(menge_el.text if menge_el is not None else None, "Menge (BT-129)")
            netto = _dec_text(
                zeile,
                "ram:SpecifiedLineTradeSettlement/ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount",
                "Zeilennetto (BT-131)",
            )
            steuer = zeile.find("ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax", _NS)
            positionen.append(
                _position_bauen(
                    nummer=_text(zeile, "ram:AssociatedDocumentLineDocument/ram:LineID"),
                    name=_text(zeile, "ram:SpecifiedTradeProduct/ram:Name"),
                    beschreibung=_text(zeile, "ram:SpecifiedTradeProduct/ram:Description"),
                    menge=menge,
                    einheit=menge_el.get("unitCode") if menge_el is not None else None,
                    preis=preis,
                    preis_basis=preis_basis,
                    netto=netto,
                    kategorie=_text(steuer, "ram:CategoryCode"),
                    satz=_dec_text(steuer, "ram:RateApplicablePercent", "Steuersatz (BT-152)"),
                )
            )

    # Zu-/Abschlaege auf Belegebene mindern/erhoehen die Steuerbasis, stehen aber
    # nicht in den Positionen -- als eigene Positionen abbilden, damit die
    # Summe der Positionen dem Nettobetrag entspricht.
    if abrechnung is not None:
        for zu_ab in abrechnung.findall("ram:SpecifiedTradeAllowanceCharge", _NS):
            betrag = _dec_text(zu_ab, "ram:ActualAmount", "Zu-/Abschlag (BT-92/99)")
            if betrag is None or betrag == 0:
                continue
            ist_zuschlag = _bool(_text(zu_ab, "ram:ChargeIndicator/udt:Indicator"))
            steuer = zu_ab.find("ram:CategoryTradeTax", _NS)
            positionen.append(
                _zuschlag_position(
                    ist_zuschlag,
                    betrag,
                    _text(zu_ab, "ram:Reason"),
                    _text(steuer, "ram:CategoryCode"),
                    _dec_text(steuer, "ram:RateApplicablePercent", "Steuersatz (BT-96/103)"),
                )
            )

    steuergruppen: list[Steuergruppe] = []
    if abrechnung is not None:
        for steuer in abrechnung.findall("ram:ApplicableTradeTax", _NS):
            if (_text(steuer, "ram:TypeCode") or "VAT") != "VAT":
                continue
            kategorie = _text(steuer, "ram:CategoryCode")
            satz = _dec_text(steuer, "ram:RateApplicablePercent", "Steuersatz (BT-119)")
            basis = _dec_text(steuer, "ram:BasisAmount", "Steuerbasisbetrag (BT-116)")
            betrag = _dec_text(steuer, "ram:CalculatedAmount", "Steuerbetrag (BT-117)")
            if kategorie is None or basis is None or betrag is None:
                raise ERechnungFehler("Eine Steueraufschlüsselung (BG-23) ist unvollständig.")
            steuergruppen.append(
                Steuergruppe(kategorie, satz if satz is not None else Decimal("0"), basis, betrag, _text(steuer, "ram:ExemptionReason"))
            )

    summen = (
        abrechnung.find("ram:SpecifiedTradeSettlementHeaderMonetarySummation", _NS) if abrechnung is not None else None
    )
    waehrung = _text(abrechnung, "ram:InvoiceCurrencyCode")
    steuer_gesamt = None
    if summen is not None:
        for el in summen.findall("ram:TaxTotalAmount", _NS):
            if el.get("currencyID") in (None, waehrung):
                steuer_gesamt = _dec(el.text, "Steuergesamtbetrag (BT-110)")
                break

    terminangaben = abrechnung.findall("ram:SpecifiedTradePaymentTerms", _NS) if abrechnung is not None else []
    faellig = None
    beschreibungen: list[str] = []
    for bedingung in terminangaben:
        faellig = faellig or _cii_datum(bedingung, "ram:DueDateDateTime/udt:DateTimeString", "Fälligkeitsdatum (BT-9)")
        beschreibung = _text(bedingung, "ram:Description")
        if beschreibung:
            beschreibungen.append(beschreibung)

    iban = None
    if abrechnung is not None:
        for zahlungsmittel in abrechnung.findall("ram:SpecifiedTradeSettlementPaymentMeans", _NS):
            iban = iban or _text(zahlungsmittel, "ram:PayeePartyCreditorFinancialAccount/ram:IBANID")

    return {
        "nummer": _text(dokument, "ram:ID"),
        "typ_code": _text(dokument, "ram:TypeCode"),
        "datum": _cii_datum(dokument, "ram:IssueDateTime/udt:DateTimeString", "Rechnungsdatum (BT-2)"),
        "faellig_am": faellig,
        "waehrung": waehrung,
        "lieferant": lieferant,
        "positionen": positionen,
        "steuergruppen": steuergruppen,
        "positions_summe": _dec_text(summen, "ram:LineTotalAmount", "Summe der Positionen (BT-106)"),
        "zuschlaege": _dec_text(summen, "ram:ChargeTotalAmount", "Summe der Zuschläge (BT-108)"),
        "abschlaege": _dec_text(summen, "ram:AllowanceTotalAmount", "Summe der Abschläge (BT-107)"),
        "netto": _dec_text(summen, "ram:TaxBasisTotalAmount", "Nettosumme (BT-109)"),
        "steuer": steuer_gesamt,
        "brutto": _dec_text(summen, "ram:GrandTotalAmount", "Bruttosumme (BT-112)"),
        "vorausgezahlt": _dec_text(summen, "ram:TotalPrepaidAmount", "Vorauszahlung (BT-113)"),
        "zahlbetrag": _dec_text(summen, "ram:DuePayableAmount", "Zahlbetrag (BT-115)"),
        "iban": iban,
        "zahlungsreferenz": _text(abrechnung, "ram:PaymentReference"),
        "zahlungsbedingungen": " / ".join(beschreibungen) or None,
    }


def _parse_ubl(root: etree._Element, ist_gutschrift_wurzel: bool) -> dict:
    lieferant_party = root.find("cac:AccountingSupplierParty/cac:Party", _NS)
    lieferant = Lieferantendaten(
        name=_text(lieferant_party, "cac:PartyLegalEntity/cbc:RegistrationName")
        or _text(lieferant_party, "cac:PartyName/cbc:Name")
    )
    if lieferant_party is not None:
        for pts in lieferant_party.findall("cac:PartyTaxScheme", _NS):
            kennung = _text(pts, "cbc:CompanyID")
            schema = (_text(pts, "cac:TaxScheme/cbc:ID") or "").upper()
            if not kennung:
                continue
            if schema == "VAT" and lieferant.ust_idnr is None:
                lieferant.ust_idnr = kennung
            elif schema != "VAT" and lieferant.steuernummer is None:
                lieferant.steuernummer = kennung
        adresse = lieferant_party.find("cac:PostalAddress", _NS)
        zeilen = [z for z in (_text(adresse, "cbc:StreetName"), _text(adresse, "cbc:AdditionalStreetName")) if z]
        lieferant.anschrift = Anschrift(
            strasse=", ".join(zeilen) or None,
            plz=_text(adresse, "cbc:PostalZone"),
            ort=_text(adresse, "cbc:CityName"),
            land=_text(adresse, "cac:Country/cbc:IdentificationCode"),
        )
        kontakt = lieferant_party.find("cac:Contact", _NS)
        lieferant.kontakt_name = _text(kontakt, "cbc:Name")
        lieferant.kontakt_telefon = _text(kontakt, "cbc:Telephone")
        lieferant.kontakt_email = _text(kontakt, "cbc:ElectronicMail")

    waehrung = _text(root, "cbc:DocumentCurrencyCode")

    positionen: list[Position] = []
    zeilen_tag = "cac:CreditNoteLine" if ist_gutschrift_wurzel else "cac:InvoiceLine"
    mengen_tag = "cbc:CreditedQuantity" if ist_gutschrift_wurzel else "cbc:InvoicedQuantity"
    for zeile in root.findall(zeilen_tag, _NS):
        if len(positionen) >= _POSITIONEN_MAX:
            raise ERechnungFehler(f"Die Rechnung hat mehr als {_POSITIONEN_MAX} Positionen.")
        menge_el = zeile.find(mengen_tag, _NS)
        steuer = zeile.find("cac:Item/cac:ClassifiedTaxCategory", _NS)
        positionen.append(
            _position_bauen(
                nummer=_text(zeile, "cbc:ID"),
                name=_text(zeile, "cac:Item/cbc:Name"),
                beschreibung=_text(zeile, "cac:Item/cbc:Description"),
                menge=_dec(menge_el.text if menge_el is not None else None, "Menge (BT-129)"),
                einheit=menge_el.get("unitCode") if menge_el is not None else None,
                preis=_dec_text(zeile, "cac:Price/cbc:PriceAmount", "Nettopreis (BT-146)"),
                preis_basis=_dec_text(zeile, "cac:Price/cbc:BaseQuantity", "Preiseinheit (BT-149)"),
                netto=_dec_text(zeile, "cbc:LineExtensionAmount", "Zeilennetto (BT-131)"),
                kategorie=_text(steuer, "cbc:ID"),
                satz=_dec_text(steuer, "cbc:Percent", "Steuersatz (BT-152)"),
            )
        )

    for zu_ab in root.findall("cac:AllowanceCharge", _NS):
        betrag = _dec_text(zu_ab, "cbc:Amount", "Zu-/Abschlag (BT-92/99)")
        if betrag is None or betrag == 0:
            continue
        steuer = zu_ab.find("cac:TaxCategory", _NS)
        positionen.append(
            _zuschlag_position(
                _bool(_text(zu_ab, "cbc:ChargeIndicator")),
                betrag,
                _text(zu_ab, "cbc:AllowanceChargeReason"),
                _text(steuer, "cbc:ID"),
                _dec_text(steuer, "cbc:Percent", "Steuersatz (BT-96/103)"),
            )
        )

    steuergruppen: list[Steuergruppe] = []
    steuer_gesamt = None
    for steuersumme in root.findall("cac:TaxTotal", _NS):
        betrag_el = steuersumme.find("cbc:TaxAmount", _NS)
        if betrag_el is not None and betrag_el.get("currencyID") not in (None, waehrung):
            continue
        if betrag_el is not None and steuer_gesamt is None:
            steuer_gesamt = _dec(betrag_el.text, "Steuergesamtbetrag (BT-110)")
        for teil in steuersumme.findall("cac:TaxSubtotal", _NS):
            schema = _text(teil, "cac:TaxCategory/cac:TaxScheme/cbc:ID")
            if schema is not None and schema.upper() != "VAT":
                continue
            kategorie = _text(teil, "cac:TaxCategory/cbc:ID")
            basis = _dec_text(teil, "cbc:TaxableAmount", "Steuerbasisbetrag (BT-116)")
            betrag = _dec_text(teil, "cbc:TaxAmount", "Steuerbetrag (BT-117)")
            if kategorie is None or basis is None or betrag is None:
                raise ERechnungFehler("Eine Steueraufschlüsselung (BG-23) ist unvollständig.")
            satz = _dec_text(teil, "cac:TaxCategory/cbc:Percent", "Steuersatz (BT-119)")
            steuergruppen.append(
                Steuergruppe(
                    kategorie, satz if satz is not None else Decimal("0"), basis, betrag,
                    _text(teil, "cac:TaxCategory/cbc:TaxExemptionReason"),
                )
            )

    summen = root.find("cac:LegalMonetaryTotal", _NS)
    faellig = _datum(_text(root, "cbc:DueDate"), "Fälligkeitsdatum (BT-9)")
    iban = None
    referenz = None
    for zahlungsmittel in root.findall("cac:PaymentMeans", _NS):
        iban = iban or _text(zahlungsmittel, "cac:PayeeFinancialAccount/cbc:ID")
        referenz = referenz or _text(zahlungsmittel, "cbc:PaymentID")
        faellig = faellig or _datum(_text(zahlungsmittel, "cbc:PaymentDueDate"), "Fälligkeitsdatum")
    bedingungen = [t for t in (_text(b, "cbc:Note") for b in root.findall("cac:PaymentTerms", _NS)) if t]

    return {
        "nummer": _text(root, "cbc:ID"),
        "typ_code": _text(root, "cbc:CreditNoteTypeCode" if ist_gutschrift_wurzel else "cbc:InvoiceTypeCode"),
        "datum": _datum(_text(root, "cbc:IssueDate"), "Rechnungsdatum (BT-2)"),
        "faellig_am": faellig,
        "waehrung": waehrung,
        "lieferant": lieferant,
        "positionen": positionen,
        "steuergruppen": steuergruppen,
        "positions_summe": _dec_text(summen, "cbc:LineExtensionAmount", "Summe der Positionen (BT-106)"),
        "zuschlaege": _dec_text(summen, "cbc:ChargeTotalAmount", "Summe der Zuschläge (BT-108)"),
        "abschlaege": _dec_text(summen, "cbc:AllowanceTotalAmount", "Summe der Abschläge (BT-107)"),
        "netto": _dec_text(summen, "cbc:TaxExclusiveAmount", "Nettosumme (BT-109)"),
        "steuer": steuer_gesamt,
        "brutto": _dec_text(summen, "cbc:TaxInclusiveAmount", "Bruttosumme (BT-112)"),
        "vorausgezahlt": _dec_text(summen, "cbc:PrepaidAmount", "Vorauszahlung (BT-113)"),
        "zahlbetrag": _dec_text(summen, "cbc:PayableAmount", "Zahlbetrag (BT-115)"),
        "iban": iban,
        "zahlungsreferenz": referenz,
        "zahlungsbedingungen": " / ".join(bedingungen) or None,
    }


def _position_bauen(
    *, nummer, name, beschreibung, menge, einheit, preis, preis_basis, netto, kategorie, satz
) -> Position:
    menge = menge if menge is not None else Decimal("1")
    effektiver_preis = preis
    if preis is not None and preis_basis not in (None, Decimal("0")):
        effektiver_preis = preis / preis_basis
    if netto is None and effektiver_preis is not None:
        netto = (menge * effektiver_preis).quantize(_CENT)
    if effektiver_preis is None and netto is not None:
        effektiver_preis = netto / menge if menge != 0 else netto
    if netto is None or effektiver_preis is None:
        raise ERechnungFehler(
            f"Position {_kurz(nummer or '?', 20)}: Preis und Zeilennetto fehlen (BT-146/BT-131)."
        )
    return Position(
        nummer=nummer,
        name=name or beschreibung or "Position",
        beschreibung=beschreibung if name and beschreibung != name else None,
        menge=menge,
        einheit=_einheit(einheit),
        einzelpreis=effektiver_preis,
        netto=netto,
        steuer_kategorie=kategorie,
        steuer_satz=satz,
    )


def _zuschlag_position(ist_zuschlag: bool, betrag: Decimal, grund: str | None, kategorie, satz) -> Position:
    betrag = abs(betrag) if ist_zuschlag else -abs(betrag)
    return Position(
        nummer=None,
        name=grund or ("Zuschlag auf Rechnungsebene" if ist_zuschlag else "Nachlass auf Rechnungsebene"),
        beschreibung=None,
        menge=Decimal("1"),
        einheit="psch",
        einzelpreis=betrag,
        netto=betrag,
        steuer_kategorie=kategorie,
        steuer_satz=satz,
    )


def _steuergruppen_aus_positionen(positionen: list[Position]) -> list[Steuergruppe]:
    summen: dict[tuple[str, Decimal], Decimal] = {}
    for p in positionen:
        schluessel = (p.steuer_kategorie or "S", p.steuer_satz if p.steuer_satz is not None else Decimal("0"))
        summen[schluessel] = summen.get(schluessel, Decimal("0")) + p.netto
    return [
        Steuergruppe(kat, satz, basis, (basis * satz / Decimal("100")).quantize(_CENT))
        for (kat, satz), basis in summen.items()
    ]


def parse_e_rechnung(xml_bytes: bytes) -> EmpfangeneRechnung:
    """Liest eine XRechnung/ZUGFeRD-CII- oder UBL-Rechnung. Wirft
    ERechnungFehler (Meldungen auf Deutsch) bei unlesbarem, unvollstaendigem
    oder nicht unterstuetztem Inhalt (Fremdwaehrung)."""
    root = _lese_xml(xml_bytes)
    qname = etree.QName(root)
    if qname.namespace == _NS["rsm"] and qname.localname == "CrossIndustryInvoice":
        syntax: Literal["cii", "ubl"] = "cii"
        roh = _parse_cii(root)
    elif (qname.namespace, qname.localname) in _UBL_WURZELN:
        syntax = "ubl"
        roh = _parse_ubl(root, ist_gutschrift_wurzel=qname.localname == "CreditNote")
    else:
        raise ERechnungFehler(
            f"Unbekanntes Wurzelelement '{_kurz(qname.localname)}': erwartet wird eine E-Rechnung im Format "
            "CII (CrossIndustryInvoice) oder UBL (Invoice/CreditNote)."
        )

    waehrung = (roh["waehrung"] or "").upper() or None
    if waehrung is not None and waehrung != "EUR":
        raise ERechnungFehler(
            f"Die Rechnung lautet auf {_kurz(waehrung, 5)}. Der Import unterstützt nur Rechnungen in EUR – "
            "bitte manuell erfassen.",
            grund="fremdwaehrung",
        )

    netto = roh["netto"]
    if netto is None and roh["positions_summe"] is not None:
        netto = roh["positions_summe"] + (roh["zuschlaege"] or 0) - (roh["abschlaege"] or 0)
    brutto = roh["brutto"]
    if brutto is None and netto is not None and roh["steuer"] is not None:
        brutto = netto + roh["steuer"]

    fehlend = []
    if not roh["nummer"]:
        fehlend.append("Rechnungsnummer (BT-1)")
    if roh["datum"] is None:
        fehlend.append("Rechnungsdatum (BT-2)")
    if waehrung is None:
        fehlend.append("Währung (BT-5)")
    if not roh["lieferant"].name:
        fehlend.append("Name des Lieferanten (BT-27)")
    if netto is None:
        fehlend.append("Nettosumme (BT-109)")
    if brutto is None:
        fehlend.append("Bruttosumme (BT-112)")
    if fehlend:
        raise ERechnungFehler([f"Pflichtfeld fehlt: {feld}" for feld in fehlend])

    steuer_gesamt = roh["steuer"] if roh["steuer"] is not None else brutto - netto
    vorausgezahlt = roh["vorausgezahlt"] or Decimal("0")
    zahlbetrag = roh["zahlbetrag"] if roh["zahlbetrag"] is not None else brutto - vorausgezahlt

    typ_code = roh["typ_code"] or ("381" if qname.localname == "CreditNote" else "380")
    ist_gutschrift = typ_code in _GUTSCHRIFT_TYPCODES or qname.localname == "CreditNote"

    steuergruppen = roh["steuergruppen"]
    abgeleitet = False
    if not steuergruppen and roh["positionen"]:
        steuergruppen = _steuergruppen_aus_positionen(roh["positionen"])
        abgeleitet = True

    rechnung = EmpfangeneRechnung(
        syntax=syntax,
        typ_code=typ_code,
        ist_gutschrift=ist_gutschrift,
        nummer=roh["nummer"],
        datum=roh["datum"],
        faellig_am=roh["faellig_am"],
        waehrung="EUR",
        lieferant=roh["lieferant"],
        positionen=roh["positionen"],
        steuergruppen=steuergruppen,
        steuergruppen_abgeleitet=abgeleitet,
        summe_netto=netto,
        summe_steuer=steuer_gesamt,
        summe_brutto=brutto,
        zahlbetrag=zahlbetrag,
        vorausgezahlt=vorausgezahlt,
        iban=roh["iban"],
        zahlungsreferenz=roh["zahlungsreferenz"],
        zahlungsbedingungen=roh["zahlungsbedingungen"],
    )
    # Gutschriften tragen in CII/UBL positive Betraege; im Rechnungseingang
    # werden sie als negative Rechnung gefuehrt. Eine Datei, die schon negative
    # Summen liefert, wird nicht doppelt negiert.
    if ist_gutschrift and rechnung.summe_brutto > 0:
        _vorzeichen_umkehren(rechnung)
    return rechnung


def _vorzeichen_umkehren(r: EmpfangeneRechnung) -> None:
    for p in r.positionen:
        p.einzelpreis = -p.einzelpreis
        p.netto = -p.netto
    for g in r.steuergruppen:
        g.basis = -g.basis
        g.steuer = -g.steuer
    r.summe_netto = -r.summe_netto
    r.summe_steuer = -r.summe_steuer
    r.summe_brutto = -r.summe_brutto
    r.zahlbetrag = -r.zahlbetrag
    r.vorausgezahlt = -r.vorausgezahlt


# --- Hybrid-PDF (ZUGFeRD/Factur-X) ------------------------------------------


def ist_pdf(daten: bytes) -> bool:
    return daten[:1024].lstrip().startswith(b"%PDF")


def extrahiere_xml_aus_pdf(pdf_bytes: bytes) -> bytes | None:
    """Liefert die eingebettete E-Rechnung (Anhangname siehe
    E_RECHNUNG_ANHANGNAMEN) oder None, wenn das PDF keine hat bzw. nicht lesbar
    ist -- ein gewoehnliches Beleg-PDF ist kein Fehler. Anzahl und Groesse der
    ausgelesenen Anhaenge sind begrenzt (Missbrauch durch Anhangs-Flut)."""
    if len(pdf_bytes) > PDF_MAX_BYTES:
        raise ERechnungFehler("Die PDF-Datei ist zu groß (max. 10 MB).", grund="zu_gross")
    # Lazy-Import: pypdf ist nur fuer diesen Pfad noetig und der Import teuer.
    from pypdf import PdfReader

    kandidaten: dict[str, bytes] = {}
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=False)
        for index, eintrag in enumerate(reader.attachment_list):
            if index >= _ANHANG_MAX_ANZAHL:
                break
            name = (eintrag.name or "").strip().lower()
            if name not in E_RECHNUNG_ANHANGNAMEN or name in kandidaten:
                continue
            try:
                deklariert = eintrag.size
            except Exception:
                deklariert = None
            if deklariert is not None and deklariert > XML_MAX_BYTES:
                raise ERechnungFehler("Die eingebettete XML-Datei ist zu groß (max. 5 MB).", grund="zu_gross")
            inhalt = eintrag.content
            if len(inhalt) > XML_MAX_BYTES:
                raise ERechnungFehler("Die eingebettete XML-Datei ist zu groß (max. 5 MB).", grund="zu_gross")
            kandidaten[name] = bytes(inhalt)
    except ERechnungFehler:
        raise
    except Exception:
        logger.info("PDF-Anhänge nicht lesbar, behandle als gewöhnliches PDF", exc_info=True)
        return None
    for name in E_RECHNUNG_ANHANGNAMEN:
        if name in kandidaten:
            return kandidaten[name]
    return None


def sha256_hex(daten: bytes) -> str:
    return hashlib.sha256(daten).hexdigest()


# --- Uebernahme in die Eingangsrechnung ---------------------------------------


def _prozent(satz: Decimal) -> str:
    text = format(satz.normalize(), "f")
    return text.replace(".", ",") + " %"


def _betrag(wert: Decimal) -> str:
    return f"{wert.quantize(_CENT):.2f}".replace(".", ",")


def _gruppenlabel(g: Steuergruppe) -> str:
    return _prozent(g.satz) if g.kategorie == "S" else f"{_prozent(g.satz)} ({g.kategorie})"


def baue_uebernahme(r: EmpfangeneRechnung) -> Uebernahme:
    hinweise: list[str] = []

    if r.ist_gutschrift:
        hinweise.append(f"Gutschrift (Typcode {r.typ_code}) – Beträge als negative Werte übernommen")
    elif r.typ_code == "384":
        hinweise.append("Rechnungskorrektur (Typcode 384) – Bezug zur korrigierten Rechnung bitte prüfen")
    elif r.typ_code != "380":
        hinweise.append(f"Dokumenttyp {r.typ_code} (nicht 380 „Rechnung“) – bitte prüfen")

    # Je (Kategorie, Satz) zusammenfassen: manche Dateien liefern denselben Satz mehrfach.
    gruppen: dict[tuple[str, Decimal], Steuergruppe] = {}
    for g in r.steuergruppen:
        schluessel = (g.kategorie, g.satz)
        if schluessel in gruppen:
            vorhanden = gruppen[schluessel]
            vorhanden.basis += g.basis
            vorhanden.steuer += g.steuer
            vorhanden.befreiungsgrund = vorhanden.befreiungsgrund or g.befreiungsgrund
        else:
            gruppen[schluessel] = Steuergruppe(g.kategorie, g.satz, g.basis, g.steuer, g.befreiungsgrund)
    ordnung = sorted(gruppen.values(), key=lambda g: abs(g.basis), reverse=True)

    if ordnung:
        mwst_satz = ordnung[0].satz
    elif r.summe_netto != 0:
        mwst_satz = (r.summe_steuer / r.summe_netto * 100).quantize(_CENT)
        hinweise.append("Steuersatz aus den Summen der Datei abgeleitet (keine Steueraufschlüsselung) – bitte prüfen")
    else:
        mwst_satz = Decimal("0")
    mwst_satz = mwst_satz.quantize(_CENT)

    if r.steuergruppen_abgeleitet:
        hinweise.append("Die Datei enthält keine Steueraufschlüsselung – aus den Positionen berechnet")
    if len(ordnung) > 1:
        labels = list(dict.fromkeys(_gruppenlabel(g) for g in ordnung))
        hinweise.append(f"Mehrere Steuersätze ({', '.join(labels)}) – Vorsteuer bitte prüfen")
    for kategorie in dict.fromkeys(g.kategorie for g in ordnung):
        text = _STEUERKATEGORIE_HINWEIS.get(kategorie)
        if text is None:
            continue
        grund = next((g.befreiungsgrund for g in ordnung if g.kategorie == kategorie and g.befreiungsgrund), None)
        hinweise.append(text + (f". Grund laut Datei: {_kurz_text(grund)}" if grund else ""))

    positionen = [_position_uebernehmen(p) for p in r.positionen]
    if not positionen:
        hinweise.append("Die Datei enthält keine Positionen – nur der Nettobetrag wurde übernommen")

    for wert in (r.summe_netto, r.summe_brutto, *(p.einzelpreis for p in positionen), *(p.menge for p in positionen)):
        if abs(wert) >= _DB_BETRAG_GRENZE:
            raise ERechnungFehler("Ein Betrag oder eine Menge überschreitet den darstellbaren Bereich.")

    if positionen:
        positionssumme = sum((p.menge * p.einzelpreis for p in positionen), Decimal("0")).quantize(_CENT)
        netto = positionssumme
        if abs(positionssumme - r.summe_netto) > _SCHWELLE:
            hinweise.append(
                f"Summe der Positionen ({_betrag(positionssumme)} EUR) weicht vom Nettobetrag "
                f"laut Datei ({_betrag(r.summe_netto)} EUR) ab – bitte prüfen"
            )
    else:
        netto = r.summe_netto.quantize(_CENT)

    system_brutto = (netto + netto * mwst_satz / Decimal("100")).quantize(_CENT)
    if abs(system_brutto - r.summe_brutto) > _SCHWELLE:
        hinweise.append(
            f"Bruttobetrag in FieldVibe ({_betrag(system_brutto)} EUR) weicht von der Datei "
            f"({_betrag(r.summe_brutto)} EUR) ab – Zahlbetrag bitte prüfen"
        )
    if r.vorausgezahlt != 0:
        hinweise.append(
            f"Laut Datei bereits gezahlt/angezahlt: {_betrag(r.vorausgezahlt)} EUR "
            f"(Zahlbetrag {_betrag(r.zahlbetrag)} EUR)"
        )

    return Uebernahme(
        lieferant_name=" ".join(r.lieferant.name.split()),
        rechnungsnummer=r.nummer,
        rechnungsdatum=r.datum,
        faellig_am=r.faellig_am,
        betrag_netto=netto,
        mwst_satz=mwst_satz,
        positionen=positionen,
        hinweise=hinweise,
        notiz=_notiz(r),
    )


def _kurz_text(text: str, maximal: int = 300) -> str:
    text = " ".join(text.split())
    return text if len(text) <= maximal else text[: maximal - 1] + "…"


def _menge_text(wert: Decimal) -> str:
    return format(wert.normalize(), "f").replace(".", ",")


def _position_uebernehmen(p: Position) -> PositionUebernahme:
    beschreibung = p.name if not p.beschreibung else f"{p.name} – {p.beschreibung}"
    beschreibung = _kurz_text(beschreibung, 500)
    passt = (
        p.menge == p.menge.quantize(_CENT)
        and p.einzelpreis == p.einzelpreis.quantize(_CENT)
        and (p.menge * p.einzelpreis).quantize(_CENT) == p.netto.quantize(_CENT)
    )
    if passt:
        return PositionUebernahme(beschreibung, p.menge, p.einheit, p.einzelpreis)
    # Menge/Preis mit mehr Nachkommastellen (Numeric(10,2) im Modell) wuerden die
    # Zeilensumme verfaelschen: Zeilennetto als Pauschale, Original im Text.
    zusatz = f" ({_menge_text(p.menge)} {p.einheit} × {_menge_text(p.einzelpreis.quantize(Decimal('0.0001')))} EUR)"
    return PositionUebernahme(beschreibung + zusatz, Decimal("1"), "psch", p.netto.quantize(_CENT))


def _notiz(r: EmpfangeneRechnung) -> str | None:
    zeilen = []
    l = r.lieferant
    kennungen = [t for t in (f"USt-IdNr. {l.ust_idnr}" if l.ust_idnr else None, f"Steuernr. {l.steuernummer}" if l.steuernummer else None) if t]
    anschrift = ", ".join(t for t in (l.anschrift.strasse, " ".join(x for x in (l.anschrift.plz, l.anschrift.ort) if x) or None) if t)
    kopf = ", ".join(t for t in (l.name, *kennungen, anschrift or None) if t)
    zeilen.append(f"Lieferant laut E-Rechnung: {_kurz_text(kopf)}")
    kontakt = ", ".join(t for t in (l.kontakt_name, l.kontakt_telefon, l.kontakt_email) if t)
    if kontakt:
        zeilen.append(f"Kontakt: {_kurz_text(kontakt)}")
    zahlung = ", ".join(
        t for t in (f"IBAN {r.iban}" if r.iban else None, f"Zahlungsreferenz {r.zahlungsreferenz}" if r.zahlungsreferenz else None) if t
    )
    if zahlung:
        zeilen.append(f"Zahlung: {_kurz_text(zahlung)}")
    if r.zahlungsbedingungen:
        zeilen.append(f"Zahlungsbedingungen: {_kurz_text(r.zahlungsbedingungen)}")
    return "\n".join(zeilen)


# --- Import in den Rechnungseingang (DB/S3) -------------------------------------


def _norm_name(name: str) -> str:
    return " ".join(name.split()).casefold()


async def _lieferant_zuordnen(
    session: AsyncSession, mandant_id: UUID, name: str
) -> tuple[Lieferant | None, bool]:
    """Zuordnung nur ueber den Namen: Lieferanten tragen (noch) keine USt-IdNr.
    Mehrere Treffer gelten als mehrdeutig und werden nicht geraten."""
    # system_session umgeht RLS (E-Mail-Import) -- Mandant daher immer explizit filtern.
    alle = (
        (
            await session.execute(
                select(Lieferant).where(Lieferant.mandant_id == mandant_id, Lieferant.geloescht_am.is_(None))
            )
        )
        .scalars()
        .all()
    )
    treffer = [lieferant for lieferant in alle if _norm_name(lieferant.name) == _norm_name(name)]
    if len(treffer) == 1:
        return treffer[0], False
    return None, len(treffer) > 1


async def _finde_duplikat(
    session: AsyncSession,
    *,
    mandant_id: UUID,
    rechnungsnummer: str,
    namen: set[str],
    lieferant_id: UUID | None,
    sha256: str,
) -> Eingangsrechnung | None:
    nummer = rechnungsnummer.strip().lower()
    kandidaten = (
        (
            await session.execute(
                select(Eingangsrechnung).where(
                    Eingangsrechnung.mandant_id == mandant_id,
                    Eingangsrechnung.geloescht_am.is_(None),
                    or_(
                        func.lower(func.trim(Eingangsrechnung.rechnungsnummer_lieferant)) == nummer,
                        Eingangsrechnung.xml_sha256 == sha256,
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    for kandidat in kandidaten:
        if kandidat.xml_sha256 == sha256:
            return kandidat
        if kandidat.rechnungsnummer_lieferant.strip().lower() != nummer:
            continue
        if (lieferant_id is not None and kandidat.lieferant_id == lieferant_id) or _norm_name(
            kandidat.lieferant_name
        ) in namen:
            return kandidat
    return None


def lese_e_rechnung_datei(daten: bytes) -> tuple[bytes, bytes | None]:
    """Liefert (xml, pdf): bei Hybrid-PDF die eingebettete XML samt Original-PDF,
    bei reiner XML (xml, None)."""
    if ist_pdf(daten):
        xml = extrahiere_xml_aus_pdf(daten)
        if xml is None:
            raise ERechnungFehler(
                "Das PDF enthält keine eingebettete E-Rechnung (erwartet: factur-x.xml, zugferd-invoice.xml "
                "oder xrechnung.xml). Gewöhnliche PDF-Belege bitte über „Rechnung erfassen“ hochladen.",
                grund="kein_xml",
            )
        return xml, daten
    if len(daten) > XML_MAX_BYTES:
        raise ERechnungFehler("Die XML-Datei ist zu groß (max. 5 MB).", grund="zu_gross")
    return daten, None


async def importiere_e_rechnung(
    session: AsyncSession,
    *,
    mandant_id: UUID,
    erstellt_von: UUID | None,
    daten: bytes,
    dateiname: str | None = None,
    email_absender: str | None = None,
    email_betreff: str | None = None,
) -> Eingangsrechnung:
    """Legt aus einer XML- oder Hybrid-PDF-Datei eine Eingangsrechnung im Status
    'offen' an. Wirft ERechnungFehler (unlesbar/unvollstaendig/Fremdwaehrung)
    bzw. ERechnungDuplikat; in beiden Faellen bleibt die Datenbank unberuehrt.
    Die Original-XML wird unveraendert archiviert (Pruefsumme ueber genau diese
    Bytes)."""
    xml_bytes, pdf_bytes = lese_e_rechnung_datei(daten)
    rechnung = parse_e_rechnung(xml_bytes)
    uebernahme = baue_uebernahme(rechnung)
    sha256 = sha256_hex(xml_bytes)

    lieferant, mehrdeutig = await _lieferant_zuordnen(session, mandant_id, uebernahme.lieferant_name)
    namen = {_norm_name(uebernahme.lieferant_name)}
    if lieferant is not None:
        namen.add(_norm_name(lieferant.name))
    duplikat = await _finde_duplikat(
        session,
        mandant_id=mandant_id,
        rechnungsnummer=uebernahme.rechnungsnummer,
        namen=namen,
        lieferant_id=lieferant.id if lieferant else None,
        sha256=sha256,
    )
    if duplikat is not None:
        raise ERechnungDuplikat(duplikat.id, duplikat.rechnungsnummer_lieferant, duplikat.lieferant_name)
    if mehrdeutig:
        uebernahme.hinweise.append(
            f"Mehrere Lieferanten mit dem Namen „{uebernahme.lieferant_name}“ – keine automatische Zuordnung"
        )

    eingangsrechnung = Eingangsrechnung(
        mandant_id=mandant_id,
        lieferant_id=lieferant.id if lieferant else None,
        lieferant_name=lieferant.name if lieferant else uebernahme.lieferant_name,
        rechnungsnummer_lieferant=uebernahme.rechnungsnummer,
        rechnungsdatum=uebernahme.rechnungsdatum,
        eingegangen_am=date.today(),
        faellig_am=uebernahme.faellig_am,
        betrag_netto=uebernahme.betrag_netto,
        mwst_satz=uebernahme.mwst_satz,
        status="offen",
        erstellt_von=erstellt_von,
        email_absender=email_absender,
        email_betreff=email_betreff,
        e_rechnung_syntax=rechnung.syntax,
        xml_sha256=sha256,
        import_hinweis=uebernahme.import_hinweis,
        notiz=uebernahme.notiz,
    )
    session.add(eingangsrechnung)
    await session.flush()
    for index, p in enumerate(uebernahme.positionen, start=1):
        session.add(
            EingangsrechnungPosition(
                mandant_id=mandant_id,
                eingangsrechnung_id=eingangsrechnung.id,
                position=index,
                beschreibung=p.beschreibung,
                menge=p.menge,
                einheit=p.einheit,
                einzelpreis=p.einzelpreis,
            )
        )

    hochgeladen: list[str] = []
    try:
        xml_key = storage_service.new_eingangsrechnung_xml_key(eingangsrechnung.mandant_id, eingangsrechnung.id)
        await storage_service.upload_bytes(xml_key, xml_bytes, "application/xml")
        hochgeladen.append(xml_key)
        eingangsrechnung.xml_object_key = xml_key
        if pdf_bytes is not None:
            beleg_key = storage_service.new_eingangsrechnung_beleg_key(
                eingangsrechnung.mandant_id, eingangsrechnung.id, dateiname or "rechnung.pdf"
            )
            await storage_service.upload_bytes(beleg_key, pdf_bytes, "application/pdf")
            hochgeladen.append(beleg_key)
            eingangsrechnung.beleg_object_key = beleg_key
        await session.flush()
    except Exception:
        for key in hochgeladen:
            try:
                await storage_service.delete_object(key)
            except Exception:
                logger.warning("Aufräumen des S3-Objekts %s nach Importfehler fehlgeschlagen", key)
        raise
    return eingangsrechnung
