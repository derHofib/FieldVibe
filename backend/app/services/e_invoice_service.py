"""ZUGFeRD-Hybrid-Rechnungen: EN16931-Pflichtfeld-Pruefung, CII-XML-Aufbau
(ueber drafthorse) und PDF/A-3-Hybrid-Erzeugung (ueber drafthorse.pdf.
attach_xml -- battle-tested, aus dem urspruenglichen factur-x-Paket
uebernommen, statt fpdf2s embed_file/set_xmp_metadata von Hand
nachzubauen).

Reine interne Pflichtfeld-Praesenzpruefung, keine Schema-/Schematron-
Validierung (siehe KoSIT-Referenzvalidator, der bewusst nicht integriert
wird -- echte Konformitaet wird spaeter manuell extern gegengeprueft).

Wird nur aktiv, wenn Mandant.firmendaten.e_rechnung_aktiv gesetzt ist
(siehe rechnung_service._rechnung_dokument_bytes) -- optional pro
Mandant, kein Zwang fuer alle Rechnungen."""
from decimal import Decimal

from drafthorse.models.accounting import ApplicableTradeTax
from drafthorse.models.document import Document
from drafthorse.models.party import TaxRegistration
from drafthorse.models.payment import PaymentTerms
from drafthorse.models.tradelines import LineItem
from drafthorse.pdf import attach_xml

from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.rechnung import Rechnung, RechnungPosition

_CENT = Decimal("0.01")
# Land-Fallback fuer Kunden ohne eigenes Laenderfeld (Kunde.adresse hat
# keinen Country-Code) -- dieses Geschaeft ist rein national taetig, siehe
# Plan "Nicht in diesem Schritt".
_LAND_FALLBACK = "DE"

# UNTDID 5305 Steuerkategorie "Exempt from tax" + der bereits im PDF
# verwendete §19-UStG-Text (pdf_service._summenblock_kleinunternehmer) --
# abgeleitet aus dem bestehenden Bool, keine neue Spalte noetig.
KLEINUNTERNEHMER_VAT_EXEMPTION_CODE = "E"
KLEINUNTERNEHMER_VAT_EXEMPTION_REASON = "Steuerbefreite Kleinunternehmerregelung nach § 19 UStG"

_KUNDE_TYPEN_MIT_UST_IDNR_PFLICHT = ("gewerbe", "oeffentlich")


def pruefe_en16931_vollstaendigkeit(
    mandant: Mandant, rechnung: Rechnung, kunde: Kunde, positionen: list[RechnungPosition]
) -> list[str]:
    """Reine Praesenzpruefung der EN16931-Pflichtfelder -- keine Schema-
    Validierung. Leere Liste = alle Pflichtangaben vorhanden, e_invoice_
    service.baue_cii_dokument() kann aufgerufen werden. Nicht-leere Liste =
    stiller Fallback auf ein normales PDF (siehe rechnung_service."""
    probleme: list[str] = []
    firmendaten = mandant.firmendaten or {}
    adresse = firmendaten.get("adresse") or {}

    if not mandant.name:
        probleme.append("Firmenname des Mandanten fehlt")
    if not (adresse.get("strasse") and adresse.get("plz") and adresse.get("ort")):
        probleme.append("Anschrift des Mandanten unvollstaendig (Strasse/PLZ/Ort)")
    if not (firmendaten.get("ust_idnr") or firmendaten.get("steuernummer")):
        probleme.append("USt-IdNr. oder Steuernummer des Mandanten fehlt")

    if not kunde.name:
        probleme.append("Name des Kunden fehlt")
    kunde_adresse = kunde.adresse or {}
    if not (kunde_adresse.get("strasse") and kunde_adresse.get("plz") and kunde_adresse.get("ort")):
        probleme.append("Anschrift des Kunden unvollstaendig (Strasse/PLZ/Ort)")
    if kunde.typ in _KUNDE_TYPEN_MIT_UST_IDNR_PFLICHT and not kunde.ust_idnr:
        probleme.append("USt-IdNr. des Kunden fehlt (Pflicht bei gewerblichen/oeffentlichen Kunden)")

    if not rechnung.rechnungsnummer:
        probleme.append("Rechnungsnummer fehlt")
    if not rechnung.leistungsdatum:
        probleme.append("Leistungsdatum fehlt")
    if not positionen and rechnung.betrag_netto <= 0:
        probleme.append("Rechnung hat weder Positionen noch einen Betrag")

    return probleme


def _land(adresse: dict | None, fallback: str) -> str:
    return (adresse or {}).get("land") or fallback


def baue_cii_dokument(
    mandant: Mandant,
    rechnung: Rechnung,
    kunde: Kunde,
    positionen: list[RechnungPosition],
    netto: Decimal,
    brutto: Decimal,
) -> Document:
    """Baut ein drafthorse-Document im EN16931-Profil. Wird nur aufgerufen,
    nachdem pruefe_en16931_vollstaendigkeit() eine leere Problemliste
    zurueckgegeben hat -- setzt also vollstaendige Pflichtangaben voraus.
    netto/brutto werden vom Aufrufer uebergeben (rechnung_service.netto_
    betrag/brutto_betrag) statt hier importiert, um einen Zirkelimport mit
    rechnung_service (das seinerseits dieses Modul aufruft) zu vermeiden."""
    firmendaten = mandant.firmendaten or {}
    seller_adresse = firmendaten.get("adresse") or {}
    seller_land = _land(seller_adresse, _LAND_FALLBACK)
    kunde_adresse = kunde.adresse or {}
    kunde_land = _land(kunde_adresse, seller_land)

    steuer = (brutto - netto).quantize(_CENT)
    ist_kleinunternehmer = bool(firmendaten.get("ist_kleinunternehmer"))

    doc = Document()
    doc.context.guideline_parameter.id = "urn:cen.eu:en16931:2017"
    doc.header.id = rechnung.rechnungsnummer
    # Rechnung (380) bzw. Rechnungskorrektur/Gutschrift (384) nach UNTDID 1001
    doc.header.type_code = "384" if rechnung.ist_storno else "380"
    doc.header.issue_date_time = rechnung.created_at.date()
    # drafthorse-Eigenheit: das Feld "Name" existiert in KEINER der
    # tatsaechlichen Factur-X/EN16931-XSD-Varianten, wird aber von der
    # Bibliothek unabhaengig vom Profil immer serialisiert, weil es intern
    # als required=True deklariert ist. Ohne diesen Eingriff schlaegt die
    # Schema-Validierung in doc.serialize() fehl.
    doc.header._data["name"] = None

    seller = doc.trade.agreement.seller
    seller.name = mandant.name
    seller.address.line_one = seller_adresse.get("strasse")
    seller.address.postcode = seller_adresse.get("plz")
    seller.address.city_name = seller_adresse.get("ort")
    seller.address.country_id = seller_land
    seller_ust_idnr = firmendaten.get("ust_idnr") or firmendaten.get("steuernummer")
    if seller_ust_idnr:
        seller.tax_registrations.add(TaxRegistration(id=("VA" if firmendaten.get("ust_idnr") else "FC", seller_ust_idnr)))

    buyer = doc.trade.agreement.buyer
    buyer.name = kunde.name
    buyer.address.line_one = kunde_adresse.get("strasse")
    buyer.address.postcode = kunde_adresse.get("plz")
    buyer.address.city_name = kunde_adresse.get("ort")
    buyer.address.country_id = kunde_land
    if kunde.ust_idnr:
        buyer.tax_registrations.add(TaxRegistration(id=("VA", kunde.ust_idnr)))

    if rechnung.leistungsdatum:
        doc.trade.delivery.event.occurrence = rechnung.leistungsdatum

    doc.trade.settlement.currency_code = "EUR"
    doc.trade.settlement.payment_reference = rechnung.rechnungsnummer

    # Als eigene Python-Werte halten, nicht ueber tax.category_code etc.
    # zuruecklesen: drafthorse-Feld-Deskriptoren liefern beim Lesen das
    # interne Element-Objekt, nicht den rohen Wert -- eine Wiederverwendung
    # ueber Rueck-Lesen wuerde das Element selbst als neuen Wert einsetzen
    # (serialisiert dann fehlerhaft).
    steuerkategorie = KLEINUNTERNEHMER_VAT_EXEMPTION_CODE if ist_kleinunternehmer else "S"
    steuersatz = Decimal("0.00") if ist_kleinunternehmer else rechnung.mwst_satz

    tax = ApplicableTradeTax()
    tax.calculated_amount = steuer
    tax.type_code = "VAT"
    tax.basis_amount = netto
    tax.category_code = steuerkategorie
    tax.rate_applicable_percent = steuersatz
    if ist_kleinunternehmer:
        tax.exemption_reason = KLEINUNTERNEHMER_VAT_EXEMPTION_REASON
    doc.trade.settlement.trade_tax.add(tax)

    if rechnung.faellig_am:
        terms = PaymentTerms()
        terms.description = f"Zahlbar bis {rechnung.faellig_am.strftime('%d.%m.%Y')}"
        terms.due = rechnung.faellig_am
        doc.trade.settlement.terms.add(terms)

    doc.trade.settlement.monetary_summation.line_total = netto
    doc.trade.settlement.monetary_summation.charge_total = Decimal("0.00")
    doc.trade.settlement.monetary_summation.allowance_total = Decimal("0.00")
    doc.trade.settlement.monetary_summation.tax_basis_total = netto
    doc.trade.settlement.monetary_summation.tax_total = (steuer, "EUR")
    doc.trade.settlement.monetary_summation.grand_total = (brutto, "EUR")
    doc.trade.settlement.monetary_summation.due_amount = brutto

    zeilen = positionen or [_synthetische_position(rechnung)]
    for index, position in enumerate(zeilen, start=1):
        line = LineItem()
        line.document.line_id = str(index)
        line.product.name = position.beschreibung
        line.agreement.net.amount = position.einzelpreis.quantize(_CENT)
        line.delivery.billed_quantity = (position.menge, "H87")
        line.settlement.trade_tax.category_code = steuerkategorie
        line.settlement.trade_tax.type_code = "VAT"
        line.settlement.trade_tax.rate_applicable_percent = steuersatz
        line.settlement.monetary_summation.total_amount = (position.menge * position.einzelpreis).quantize(_CENT)
        doc.trade.items.add(line)

    return doc


def _synthetische_position(rechnung: Rechnung) -> RechnungPosition:
    """Rechnungen ohne eigene Positionen (der einfache Fall aus Phase 6)
    brauchen trotzdem mindestens eine CII-Rechnungszeile -- analog zum
    bestehenden Fallback in rechnung_service.netto_betrag()."""
    return RechnungPosition(
        position=1,
        beschreibung=f"Rechnung {rechnung.rechnungsnummer}",
        menge=Decimal("1"),
        einheit="Stk",
        einzelpreis=rechnung.betrag_netto,
    )


def cii_xml_bytes(document: Document) -> bytes:
    return document.serialize(schema="FACTUR-X_EN16931")


def baue_hybrid_pdf(pdf_bytes: bytes, xml_bytes: bytes) -> bytes:
    """Bettet die CII-XML in das bereits erzeugte PDF ein (embed_file,
    OutputIntent-Uebernahme, Factur-X-XMP-Metadaten) -- drafthorse.pdf.
    attach_xml() macht das vollstaendig, keine eigene fpdf2-Nachbildung
    noetig. Das Quell-PDF muss bereits mit pdf_service.generate_rechnung_pdf(
    ..., pdfa_output_intent=True) erzeugt worden sein, sonst bleibt das
    Hybrid-PDF ohne ICC-OutputIntent."""
    return attach_xml(pdf_bytes, xml_bytes, level="EN 16931")
