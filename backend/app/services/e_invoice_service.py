"""ZUGFeRD-Hybrid-Rechnungen: EN16931-Pflichtfeld-Pruefung, CII-XML-Aufbau
(ueber drafthorse) und PDF/A-3-Hybrid-Erzeugung (ueber drafthorse.pdf.
attach_xml -- battle-tested, aus dem urspruenglichen factur-x-Paket
uebernommen, statt fpdf2s embed_file/set_xmp_metadata von Hand
nachzubauen).

Die interne Pruefung ist eine reine Pflichtfeld-Praesenzpruefung. Die
Konformitaet der erzeugten XML gegen die EN-16931-Geschaeftsregeln
(Schematron) belegen scripts/e-rechnung/ und tests/test_e_rechnung_
konformitaet.py, siehe docs/konzepte/E_RECHNUNG_PRUEFUNG.md.

Wird nur aktiv, wenn der Modus des Mandanten (firmendaten.e_rechnung_modus
aus/b2b/alle, siehe e_rechnung_gilt) es fuer den Kunden verlangt -- optional
pro Mandant, kein Zwang fuer alle Rechnungen. Das Profil (EN 16931 bzw.
ZUGFeRD oder XRechnung) waehlt profil_fuer je Kunde. Fehlen dann Pflichtangaben,
scheitert der Versand (kein stiller Fallback aufs normale PDF)."""
import re
from decimal import Decimal

from drafthorse.models.accounting import ApplicableTradeTax, CategoryTradeTax, TradeAllowanceCharge
from drafthorse.models.document import Document
from drafthorse.models.note import IncludedNote
from drafthorse.models.party import TaxRegistration
from drafthorse.models.payment import PaymentMeans, PaymentTerms
from drafthorse.models.tradelines import LineItem
from drafthorse.pdf import attach_xml

from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.rechnung import Rechnung, RechnungPosition
from app.services import steuer_service
from app.services.steuer_service import SteuerGruppe

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

# UNTDID 1001: 380 Handelsrechnung, 381 Gutschrift, 384 Rechnungskorrektur
# (Storno), 386 Vorauszahlungsrechnung. Die Schlussrechnung ist eine normale
# Handelsrechnung: die Abschlaege stehen als Abzugszeilen darauf.
_TYPE_CODE_NACH_ART = {"rechnung": "380", "schluss": "380", "abschlag": "386", "gutschrift": "381"}


def type_code_fuer(rechnung: Rechnung, profil: str = "en16931") -> str:
    if rechnung.ist_storno:
        return "384"
    # BR-DE-17: die XRechnung kennt 386 nicht; Abschlagsrechnungen laufen dort als
    # Teilrechnung (326).
    if profil == "xrechnung" and rechnung.rechnungsart == "abschlag":
        return "326"
    return _TYPE_CODE_NACH_ART.get(rechnung.rechnungsart, "380")


E_RECHNUNG_MODI = ("aus", "b2b", "alle")

EN16931_PROFIL = "en16931"
XRECHNUNG_PROFIL = "xrechnung"
EN16931_KENNUNG = "urn:cen.eu:en16931:2017"
# Kennung laut XRechnung-Schematron 2.6.0 (common.sch): seit XRechnung 3.0 "xeinkauf.de",
# nicht mehr "xoev-de:kosit:standard" wie in 2.x.
XRECHNUNG_KENNUNG = "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
# Elektronische Adresse (BT-49) des Kaeufers: EAS-Code 0204 = Leitweg-ID; BT-34 des
# Verkaeufers: EM = E-Mail.
_EAS_LEITWEG_ID = "0204"
_EAS_EMAIL = "EM"

_EMAIL_MUSTER = re.compile(r"[^@\s]+@([^@.\s]+\.)+[^@.\s]+")
_IBAN_MUSTER = re.compile(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}")


def e_rechnung_modus(firmendaten: dict | None) -> str:
    """Wirksamer Modus: der gespeicherte, sonst abgeleitet aus dem aelteren
    e_rechnung_aktiv (true -> alle, sonst aus) -- Mandanten und Tests ohne den neuen
    Schluessel verhalten sich damit wie vorher."""
    fd = firmendaten or {}
    if fd.get("e_rechnung_modus") in E_RECHNUNG_MODI:
        return fd["e_rechnung_modus"]
    return "alle" if fd.get("e_rechnung_aktiv") else "aus"


def e_rechnung_gilt(mandant: Mandant, kunde: Kunde) -> bool:
    modus = e_rechnung_modus(mandant.firmendaten)
    if modus == "alle":
        return True
    return modus == "b2b" and kunde.ist_gewerblich


def profil_fuer(kunde: Kunde) -> str:
    """Explizites Kundenformat gewinnt; ohne Angabe entscheidet die Leitweg-ID."""
    if kunde.e_rechnung_format == "xrechnung":
        return XRECHNUNG_PROFIL
    if kunde.e_rechnung_format == "zugferd":
        return EN16931_PROFIL
    return XRECHNUNG_PROFIL if (kunde.leitweg_id or "").strip() else EN16931_PROFIL


def iban_gueltig(iban: str) -> bool:
    iban = "".join(iban.split()).upper()
    if not _IBAN_MUSTER.fullmatch(iban):
        return False
    umgestellt = iban[4:] + iban[:4]
    return int("".join(str(int(zeichen, 36)) for zeichen in umgestellt)) % 97 == 1


def pruefe_e_rechnung(
    mandant: Mandant, rechnung: Rechnung, kunde: Kunde, positionen: list[RechnungPosition]
) -> list[str]:
    """EN16931-Pflichtfelder plus, beim Profil XRechnung, die Pflichtangaben der
    Zusatzregeln BR-DE-*. Der Versandweg ruft ausschliesslich diese Funktion."""
    probleme = pruefe_en16931_vollstaendigkeit(mandant, rechnung, kunde, positionen)
    if profil_fuer(kunde) == XRECHNUNG_PROFIL:
        probleme += pruefe_xrechnung_zusatz(mandant, kunde)
    return probleme


def pruefe_xrechnung_zusatz(mandant: Mandant, kunde: Kunde) -> list[str]:
    """Angaben, die nur die XRechnung (CIUS) zusaetzlich zur EN 16931 verlangt. Anschrift
    von Verkaeufer und Kaeufer (BR-DE-3/4/8/9) und Steuerkennung (BR-DE-16) deckt die
    EN16931-Pruefung schon ab."""
    fd = mandant.firmendaten or {}
    probleme: list[str] = []
    if not (kunde.leitweg_id or "").strip():
        probleme.append("Leitweg-ID des Kunden fehlt (Pflicht für die XRechnung, BT-10 / BR-DE-15)")

    telefon = (fd.get("telefon") or "").strip()
    if not telefon:
        probleme.append("Telefonnummer des Mandanten fehlt (XRechnung: Verkäufer-Kontakt, BR-DE-6)")
    elif sum(zeichen.isdigit() for zeichen in telefon) < 3:
        probleme.append("Telefonnummer des Mandanten braucht mindestens drei Ziffern (BR-DE-27)")
    email = (fd.get("email") or "").strip()
    if not email:
        probleme.append("E-Mail-Adresse des Mandanten fehlt (XRechnung: Verkäufer-Kontakt, BR-DE-7)")
    elif not _EMAIL_MUSTER.fullmatch(email):
        probleme.append("E-Mail-Adresse des Mandanten ist ungültig (BR-DE-28)")

    iban = (fd.get("iban") or "").strip()
    if not iban:
        probleme.append("IBAN des Mandanten fehlt (XRechnung: Zahlungsangaben, BR-DE-1 / BR-DE-23)")
    elif not iban_gueltig(iban):
        probleme.append("IBAN des Mandanten ist ungültig (Prüfsumme, BR-DE-19)")
    return probleme


def pruefe_en16931_vollstaendigkeit(
    mandant: Mandant, rechnung: Rechnung, kunde: Kunde, positionen: list[RechnungPosition]
) -> list[str]:
    """Reine Praesenzpruefung der EN16931-Pflichtfelder -- keine Schema-
    Validierung. Leere Liste = alle Pflichtangaben vorhanden, e_invoice_
    service.baue_cii_dokument() kann aufgerufen werden. Nicht-leere Liste =
    der Versand wird mit dieser Liste abgelehnt (rechnung_service.pruefe_versand).
    Steuergruende und die 13b-Voraussetzungen am Kunden prueft
    steuer_service.pruefe_steuer_fuer_versand."""
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
    # Behoerden haben haeufig keine USt-IdNr.; die XRechnung adressiert sie ueber die Leitweg-ID.
    ust_idnr_entbehrlich = kunde.typ == "oeffentlich" and profil_fuer(kunde) == XRECHNUNG_PROFIL
    if kunde.typ in _KUNDE_TYPEN_MIT_UST_IDNR_PFLICHT and not kunde.ust_idnr and not ust_idnr_entbehrlich:
        probleme.append("USt-IdNr. des Kunden fehlt (Pflicht bei gewerblichen/oeffentlichen Kunden)")

    if not rechnung.rechnungsnummer:
        probleme.append("Rechnungsnummer fehlt")
    if not rechnung.leistungsdatum:
        probleme.append("Leistungsdatum fehlt")
    if not positionen and rechnung.betrag_netto <= 0:
        probleme.append("Rechnung hat weder Positionen noch einen Betrag")

    # Reverse Charge: BT-31 (Verkaeufer) und BT-48 (Kaeufer) muessen USt-IdNrn.
    # sein -- eine Steuernummer reicht beim Verkaeufer hier nicht.
    if any(p.steuer_kategorie == "AE" for p in positionen):
        if not (firmendaten.get("ust_idnr") or "").strip():
            probleme.append(steuer_service.MELDUNG_MANDANT_UST_IDNR_13B)
        if not (kunde.ust_idnr or "").strip():
            probleme.append(steuer_service.MELDUNG_KUNDE_UST_IDNR_13B)

    return probleme


def _betrag(wert: Decimal) -> Decimal:
    # Stornobelege rechnen mit negativen Betraegen; 0 * -1 ergibt "-0.00", das die
    # Regeln BR-Z-09/BR-E-09/BR-AE-09 ("Steuerbetrag = 0") als Verstoss werten.
    return Decimal("0.00") if wert == 0 else wert


def _land(adresse: dict | None, fallback: str) -> str:
    return (adresse or {}).get("land") or fallback


def baue_cii_dokument(
    mandant: Mandant,
    rechnung: Rechnung,
    kunde: Kunde,
    positionen: list[RechnungPosition],
    netto: Decimal,
    brutto: Decimal,
    *,
    bezug_rechnung: Rechnung | None = None,
    angerechnete_abschlaege: list[Rechnung] | None = None,
    profil: str = EN16931_PROFIL,
    hinweise: list[str] | None = None,
) -> Document:
    """Baut ein drafthorse-Document im EN16931- oder XRechnung-Profil (profil). Wird
    nur aufgerufen, nachdem pruefe_e_rechnung() eine leere Problemliste
    zurueckgegeben hat -- setzt also vollstaendige Pflichtangaben voraus.
    netto/brutto werden vom Aufrufer uebergeben (rechnung_service.netto_
    betrag/brutto_betrag) statt hier importiert, um einen Zirkelimport mit
    rechnung_service (das seinerseits dieses Modul aufruft) zu vermeiden.

    bezug_rechnung (Gutschrift): die Ursprungsrechnung als BT-25. Das Factur-X-
    Profil EN 16931 erlaubt nur EINE InvoiceReferencedDocument; deshalb stehen
    die angerechneten Abschlaege einer Schlussrechnung (mehrere moeglich) als
    Rechnungsvermerk (BT-22) statt als Referenz.

    hinweise: zusaetzliche Rechnungsvermerke (BT-22), z. B. die Hinweise fuer
    Privatkunden aus privatkunden_service -- derselbe Text wie im PDF."""
    firmendaten = mandant.firmendaten or {}
    seller_adresse = firmendaten.get("adresse") or {}
    seller_land = _land(seller_adresse, _LAND_FALLBACK)
    kunde_adresse = kunde.adresse or {}
    kunde_land = _land(kunde_adresse, seller_land)

    netto, brutto = _betrag(netto), _betrag(brutto)
    steuer = _betrag((brutto - netto).quantize(_CENT))
    ist_kleinunternehmer = bool(firmendaten.get("ist_kleinunternehmer"))

    doc = Document()
    ist_xrechnung = profil == XRECHNUNG_PROFIL
    doc.context.guideline_parameter.id = XRECHNUNG_KENNUNG if ist_xrechnung else EN16931_KENNUNG
    doc.header.id = rechnung.rechnungsnummer
    doc.header.type_code = type_code_fuer(rechnung, profil)
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
        if not firmendaten.get("ust_idnr"):
            # BR-CO-26 verlangt BT-29, BT-30 oder BT-31; eine Steuernummer (BT-32) allein
            # genuegt nicht. Ohne USt-IdNr. und Handelsregisternummer bleibt als
            # Verkaeuferkennung (BT-29) nur die Steuernummer.
            seller.id = seller_ust_idnr

    buyer = doc.trade.agreement.buyer
    buyer.name = kunde.name
    buyer.address.line_one = kunde_adresse.get("strasse")
    buyer.address.postcode = kunde_adresse.get("plz")
    buyer.address.city_name = kunde_adresse.get("ort")
    buyer.address.country_id = kunde_land
    if kunde.ust_idnr:
        buyer.tax_registrations.add(TaxRegistration(id=("VA", kunde.ust_idnr)))

    leitweg = (kunde.leitweg_id or "").strip()
    if leitweg:
        doc.trade.agreement.buyer_reference = leitweg  # BT-10
    if ist_xrechnung:
        _xrechnung_angaben(doc, mandant, leitweg)

    if rechnung.leistungsdatum:
        doc.trade.delivery.event.occurrence = rechnung.leistungsdatum

    doc.trade.settlement.currency_code = "EUR"
    doc.trade.settlement.payment_reference = rechnung.rechnungsnummer
    for text in hinweise or []:
        doc.header.notes.add(IncludedNote(content=text))

    # BR-DE-26: ein Stornobeleg (384) soll die korrigierte Rechnung referenzieren; das
    # verlangt nur die XRechnung, das ZUGFeRD-Profil laesst die Referenz weg.
    if bezug_rechnung is not None and (rechnung.rechnungsart == "gutschrift" or (ist_xrechnung and rechnung.ist_storno)):
        bezug = doc.trade.settlement.invoice_referenced_document
        bezug.issuer_assigned_id = bezug_rechnung.rechnungsnummer
        bezug.issue_date_time = bezug_rechnung.created_at.date()
    if rechnung.rechnungsart == "gutschrift":
        if rechnung.gutschrift_grund:
            doc.header.notes.add(IncludedNote(content=f"Grund der Gutschrift: {rechnung.gutschrift_grund}"))
    if angerechnete_abschlaege:
        angerechnet = "; ".join(
            f"{a.rechnungsnummer} vom {a.created_at.strftime('%d.%m.%Y')}" for a in angerechnete_abschlaege
        )
        doc.header.notes.add(
            IncludedNote(content=f"Netto angerechnete Abschlagsrechnungen: {angerechnet}")
        )

    # Als eigene Python-Werte halten, nicht ueber tax.category_code etc.
    # zuruecklesen: drafthorse-Feld-Deskriptoren liefern beim Lesen das
    # interne Element-Objekt, nicht den rohen Wert -- eine Wiederverwendung
    # ueber Rueck-Lesen wuerde das Element selbst als neuen Wert einsetzen
    # (serialisiert dann fehlerhaft).
    # Je Gruppe ein Steuerblock mit Kategorie, Satz und -- bei E/AE -- dem
    # Befreiungsgrund aus dem Katalog.
    if ist_kleinunternehmer:
        # Eine Befreiung fuer den ganzen Beleg, unabhaengig von gespeicherten Saetzen.
        gruppen = [SteuerGruppe(KLEINUNTERNEHMER_VAT_EXEMPTION_CODE, Decimal("0.00"), netto, steuer)]
    else:
        gruppen = steuer_service.steuer_gruppen(rechnung, positionen)
    for gruppe in gruppen:
        tax = ApplicableTradeTax()
        tax.calculated_amount = _betrag(gruppe.steuer)
        tax.type_code = "VAT"
        tax.basis_amount = _betrag(gruppe.netto)
        tax.category_code = gruppe.kategorie
        tax.rate_applicable_percent = gruppe.satz
        if ist_kleinunternehmer:
            tax.exemption_reason = KLEINUNTERNEHMER_VAT_EXEMPTION_REASON
        elif gruppe.kategorie in ("E", "AE") and gruppe.hinweis:
            tax.exemption_reason = gruppe.hinweis
        elif gruppe.kategorie == "Z" and gruppe.hinweis:
            # BR-Z-10: "Zero rated" darf keinen Befreiungsgrund tragen -- der
            # gesetzliche Hinweis steht stattdessen als Rechnungsvermerk (BT-22).
            doc.header.notes.add(IncludedNote(content=gruppe.hinweis))
        doc.trade.settlement.trade_tax.add(tax)

    if rechnung.faellig_am:
        terms = PaymentTerms()
        terms.description = f"Zahlbar bis {rechnung.faellig_am.strftime('%d.%m.%Y')}"
        terms.due = rechnung.faellig_am
        doc.trade.settlement.terms.add(terms)

    zeilen = positionen or [_synthetische_position(rechnung)]
    # Zeilensummen je Steuergruppe: BR-CO-10/BR-S-08 u. a. verlangen, dass sich die
    # Belegsummen aus den (auf Cent gerundeten) Zeilenbetraegen ergeben, waehrend
    # steuer_service je Gruppe erst die ungerundete Summe rundet (siehe dort).
    zeilen_summen: dict[tuple[str, Decimal], Decimal] = {}
    for index, position in enumerate(zeilen, start=1):
        line = LineItem()
        line.document.line_id = str(index)
        line.product.name = position.beschreibung
        zeilen_kategorie, zeilen_satz = _steuer_der_zeile(position, rechnung, ist_kleinunternehmer)
        zeilen_netto = _betrag(steuer_service.runde_cent(position.menge * position.einzelpreis))
        zeilen_summen[(zeilen_kategorie, zeilen_satz)] = (
            zeilen_summen.get((zeilen_kategorie, zeilen_satz), Decimal("0")) + zeilen_netto
        )
        einzelpreis, menge = _betrag(position.einzelpreis.quantize(_CENT)), position.menge
        if einzelpreis < 0:
            # BR-27: der Nettopreis (BT-146) darf nicht negativ sein. Stornozeilen
            # tragen den negativen Preis intern; hier wandert das Vorzeichen in die
            # Menge, der Zeilenbetrag bleibt gleich.
            einzelpreis, menge = -einzelpreis, -menge
        line.agreement.net.amount = einzelpreis
        line.delivery.billed_quantity = (menge, "H87")
        line.settlement.trade_tax.category_code = zeilen_kategorie
        line.settlement.trade_tax.type_code = "VAT"
        line.settlement.trade_tax.rate_applicable_percent = zeilen_satz
        line.settlement.monetary_summation.total_amount = zeilen_netto
        doc.trade.items.add(line)

    # Rundungsdifferenz zwischen Gruppennetto und Summe der Zeilenbetraege als
    # Zu-/Abschlag in der Steuergruppe, damit die Belegsummen mit PDF und
    # Buchhaltung uebereinstimmen und die Zeilen unverfaelscht bleiben.
    zuschlaege = Decimal("0.00")
    abschlaege = Decimal("0.00")
    for gruppe in gruppen:
        differenz = gruppe.netto - zeilen_summen.get((gruppe.kategorie, gruppe.satz), Decimal("0"))
        if not differenz:
            continue
        korrektur = TradeAllowanceCharge()
        korrektur.indicator = differenz > 0
        korrektur.actual_amount = abs(differenz)
        korrektur.reason = "Rundungsdifferenz"
        korrektur_steuer = CategoryTradeTax()
        korrektur_steuer.type_code = "VAT"
        korrektur_steuer.category_code = gruppe.kategorie
        korrektur_steuer.rate_applicable_percent = gruppe.satz
        korrektur.trade_tax.add(korrektur_steuer)
        doc.trade.settlement.allowance_charge.add(korrektur)
        if differenz > 0:
            zuschlaege += differenz
        else:
            abschlaege -= differenz

    doc.trade.settlement.monetary_summation.line_total = sum(zeilen_summen.values(), Decimal("0.00"))
    doc.trade.settlement.monetary_summation.charge_total = zuschlaege
    doc.trade.settlement.monetary_summation.allowance_total = abschlaege
    doc.trade.settlement.monetary_summation.tax_basis_total = netto
    doc.trade.settlement.monetary_summation.tax_total = (steuer, "EUR")
    # CII-DT-031: currencyID darf nur am Steuerbetrag (BT-110) stehen, nicht am Gesamtbetrag.
    doc.trade.settlement.monetary_summation.grand_total = brutto
    doc.trade.settlement.monetary_summation.due_amount = brutto

    return doc


def _xrechnung_angaben(doc: Document, mandant: Mandant, leitweg: str) -> None:
    """Angaben, die die XRechnung zusaetzlich zur EN 16931 verlangt (Vollstaendigkeit
    stellt pruefe_xrechnung_zusatz sicher): Verkaeufer-Kontakt BG-6, Zahlungsangaben
    BG-16/17 und die elektronischen Adressen BT-34/BT-49."""
    fd = mandant.firmendaten or {}
    seller = doc.trade.agreement.seller
    email = fd["email"].strip()
    # BT-41 verlangt eine Person oder Abteilung; ohne eigenes Feld dafuer: die
    # Geschaeftsfuehrung, sonst der Firmenname als Abteilung.
    if (fd.get("geschaeftsfuehrung") or "").strip():
        seller.contact.person_name = fd["geschaeftsfuehrung"].strip()
    else:
        seller.contact.department_name = mandant.name
    seller.contact.telephone.number = fd["telefon"].strip()
    seller.contact.email.address = email
    seller.electronic_address.uri_ID = (_EAS_EMAIL, email)
    doc.trade.agreement.buyer.electronic_address.uri_ID = (_EAS_LEITWEG_ID, leitweg)

    zahlung = PaymentMeans()
    zahlung.type_code = "58"  # SEPA-Ueberweisung; BR-DE-23 verlangt dann BG-17 (IBAN)
    zahlung.payee_account.iban = "".join(fd["iban"].split()).upper()
    if (fd.get("bic") or "").strip():
        zahlung.payee_institution.bic = fd["bic"].strip()
    doc.trade.settlement.payment_means.add(zahlung)


def _steuer_der_zeile(
    position: RechnungPosition, rechnung: Rechnung, ist_kleinunternehmer: bool
) -> tuple[str, Decimal]:
    # Als eigene Python-Werte zurueckgeben, nicht ueber tax.category_code etc.
    # zuruecklesen (siehe drafthorse-Hinweis in baue_cii_dokument). Synthetische
    # und nicht gespeicherte Positionen haben keine Steuerfelder und erben vom
    # Beleg.
    if ist_kleinunternehmer:
        return KLEINUNTERNEHMER_VAT_EXEMPTION_CODE, Decimal("0.00")
    satz = (rechnung.mwst_satz if position.steuer_satz is None else position.steuer_satz).quantize(_CENT)
    kategorie = position.steuer_kategorie or steuer_service.kategorie_fuer_beleg_satz(satz)
    return kategorie, satz


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


def baue_hybrid_pdf(pdf_bytes: bytes, xml_bytes: bytes, profil: str = EN16931_PROFIL) -> bytes:
    """Bettet die CII-XML in das bereits erzeugte PDF ein (embed_file,
    OutputIntent-Uebernahme, Factur-X-XMP-Metadaten) -- drafthorse.pdf.
    attach_xml() macht das vollstaendig, keine eigene fpdf2-Nachbildung
    noetig. Das Quell-PDF muss bereits mit pdf_service.generate_rechnung_pdf(
    ..., pdfa_output_intent=True) erzeugt worden sein, sonst bleibt das
    Hybrid-PDF ohne ICC-OutputIntent."""
    return attach_xml(pdf_bytes, xml_bytes, level="XRECHNUNG" if profil == XRECHNUNG_PROFIL else "EN 16931")
