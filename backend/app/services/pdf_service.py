from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from fpdf import FPDF
from fpdf.enums import OutputIntentSubType, XPos, YPos
from fpdf.output import PDFICCProfile
from fpdf.util import builtin_srgb2014_bytes

from app.models.angebot import Angebot, AngebotPosition
from app.models.bestellung import Bestellung, BestellungPosition
from app.models.formular import GRID_SPALTEN, VorgangFormular
from app.models.kunde import Kunde
from app.models.lieferant import Lieferant
from app.models.mandant import Mandant
from app.models.mangel import Mangel
from app.models.rechnung import Rechnung, RechnungPosition
from app.models.user import User
from app.models.vorgang import Vorgang
from app.models.zeiterfassung import Zeiterfassung
from app.schemas.zeiterfassung import ZEITERFASSUNG_KATEGORIE_LABEL

# fpdf2s core fonts (Helvetica/Times/Courier) sind Windows-1252-kodiert --
# das deckt deutsche Umlaute/ß ab, aber NICHT das Euro-Zeichen zuverlaessig
# ueber alle Renderer hinweg. "EUR" statt "€" spart eine Custom-Font-
# Einbettung, ohne dass Betraege missverstaendlich waeren.
_WAEHRUNG = "EUR"

# Freitext im Formular-Baukasten (Feldlabels, Antworten) kommt direkt vom
# Nutzer -- Zeichen ausserhalb von Windows-1252 (z.B. "Ω", "∆") liess fpdf2
# bislang mit einer FPDFUnicodeEncodingException abbrechen und den gesamten
# PDF-Export mit 500 fehlschlagen. _pdf_safe_text() ersetzt die gaengigsten
# technischen Sonderzeichen durch ASCII-Entsprechungen und faengt alles
# uebrige als Fallback ab, damit ein einzelnes unbekanntes Zeichen nie mehr
# den kompletten Export zum Absturz bringt.
_PDF_TEXT_REPLACEMENTS: dict[str, str] = {
    "Ω": "Ohm",
    "μ": "u",
    "µ": "u",
    "Δ": "d",
    "∆": "d",
    "√": "sqrt",
    "±": "+/-",
    "→": "->",
    "≈": "~",
    "≤": "<=",
    "≥": ">=",
    "–": "-",
    "—": "-",
    "…": "...",
}


def _pdf_safe_text(text: object) -> str:
    s = "" if text is None else str(text)
    for src, dst in _PDF_TEXT_REPLACEMENTS.items():
        s = s.replace(src, dst)
    try:
        s.encode("cp1252")
    except UnicodeEncodeError:
        s = s.encode("cp1252", errors="replace").decode("cp1252")
    return s


def _fmt_zahl(zahl: Decimal) -> str:
    return f"{zahl:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_betrag(betrag: Decimal) -> str:
    return f"{_fmt_zahl(betrag)} {_WAEHRUNG}"


def _fmt_datum(d: date | datetime | None) -> str:
    if d is None:
        return "-"
    return d.strftime("%d.%m.%Y")


def _kopf(pdf: FPDF, mandant: Mandant, titel: str, nummer: str, kunde: Kunde) -> None:
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, mandant.name, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    # Eigene Anschrift + Steuernummer/USt-IdNr. (§14 Abs. 4 Nr. 1+2 UStG) --
    # ohne diese beiden Angaben ist die Rechnung fuer den Empfaenger nicht
    # vorsteuerabzugsfaehig.
    fd = mandant.firmendaten or {}
    pdf.set_font("Helvetica", "", 9)
    for zeile in _adresse_zeilen(fd.get("adresse")):
        pdf.cell(0, 5, zeile, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if fd.get("steuernummer"):
        pdf.cell(0, 5, f"Steuernummer: {fd['steuernummer']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    elif fd.get("ust_idnr"):
        pdf.cell(0, 5, f"USt-IdNr.: {fd['ust_idnr']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"{titel} {nummer}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "Kunde", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, kunde.name, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if kunde.adresse:
        strasse = kunde.adresse.get("strasse") if isinstance(kunde.adresse, dict) else None
        ort = kunde.adresse.get("ort") if isinstance(kunde.adresse, dict) else None
        if strasse:
            pdf.cell(0, 6, str(strasse), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if ort:
            pdf.cell(0, 6, str(ort), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(6)


def _positionen_tabelle(pdf: FPDF, positionen: list[AngebotPosition]) -> Decimal:
    pdf.set_font("Helvetica", "B", 10)
    spalten = (("Pos.", 12), ("Beschreibung", 90), ("Menge", 22), ("Einheit", 22), ("Preis", 22), ("Gesamt", 22))
    for label, breite in spalten:
        pdf.cell(breite, 8, label, border=1)
    pdf.ln()

    pdf.set_font("Helvetica", "", 10)
    gesamt_netto = Decimal("0")
    for p in sorted(positionen, key=lambda x: x.position):
        zeilen_gesamt = p.menge * p.einzelpreis
        gesamt_netto += zeilen_gesamt
        pdf.cell(12, 8, str(p.position), border=1)
        pdf.cell(90, 8, p.beschreibung[:55], border=1)
        pdf.cell(22, 8, f"{p.menge:g}", border=1, align="R")
        pdf.cell(22, 8, p.einheit, border=1)
        pdf.cell(22, 8, _fmt_betrag(p.einzelpreis), border=1, align="R")
        pdf.cell(22, 8, _fmt_betrag(zeilen_gesamt), border=1, align="R")
        pdf.ln()
    return gesamt_netto


def _summenblock(pdf: FPDF, gesamt_netto: Decimal, mwst_satz: Decimal) -> None:
    mwst_betrag = gesamt_netto * mwst_satz / Decimal("100")
    gesamt_brutto = gesamt_netto + mwst_betrag
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 10)
    for label, wert in (
        ("Netto", _fmt_betrag(gesamt_netto)),
        (f"MwSt. ({mwst_satz:g}%)", _fmt_betrag(mwst_betrag)),
    ):
        pdf.cell(148, 7, "", border=0)
        pdf.cell(22, 7, label)
        pdf.cell(22, 7, wert, align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(148, 8, "", border=0)
    pdf.cell(22, 8, "Gesamt")
    pdf.cell(22, 8, _fmt_betrag(gesamt_brutto), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _summenblock_kleinunternehmer(pdf: FPDF, gesamt_netto: Decimal) -> None:
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(148, 8, "", border=0)
    pdf.cell(22, 8, "Gesamt")
    pdf.cell(22, 8, _fmt_betrag(gesamt_netto), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 8)
    pdf.multi_cell(0, 4, "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.")


class _AngebotPDF(FPDF):
    """Eigene FPDF-Subklasse nur fuer generate_angebot_pdf() -- Kopf-/
    Fusszeile muessen sich pro Seite automatisch wiederholen (Briefkopf auf
    Seite 1 vollstaendig, ab Seite 2 nur noch eine schmale Kennzeile;
    Bankverbindung/Rechtliches unten auf jeder Seite), was fpdf2 nur ueber
    header()/footer() anbietet -- die generischen _kopf()/_positionen_
    tabelle()/_summenblock() oben werden von Rechnung/Bestellung/Maengel-
    Protokoll weiterverwendet und bleiben deshalb unveraendert."""

    def __init__(self, mandant: Mandant, angebot: Angebot, logo_bytes: bytes | None):
        super().__init__()
        self._mandant = mandant
        self._angebot = angebot
        self._logo_bytes = logo_bytes

    def header(self) -> None:
        if self.page_no() == 1:
            if self._logo_bytes:
                self.image(BytesIO(self._logo_bytes), x=20, y=15, h=18)
            else:
                self.set_xy(20, 15)
                self.set_font("Helvetica", "B", 20)
                self.set_text_color(70, 70, 70)
                self.cell(0, 10, self._mandant.name)
                self.set_text_color(0, 0, 0)
        else:
            self.set_xy(20, 12)
            self.set_font("Helvetica", "", 9)
            self.set_text_color(120, 120, 120)
            self.cell(
                0,
                6,
                f"{self._mandant.name} · Angebot {self._angebot.angebotsnummer} · Seite {self.page_no()}",
            )
            self.set_text_color(0, 0, 0)

    def footer(self) -> None:
        fd = self._mandant.firmendaten or {}
        teile = [self._mandant.name]
        if fd.get("bank_name"):
            teile.append(str(fd["bank_name"]))
        if fd.get("iban"):
            teile.append(f"IBAN: {fd['iban']}")
        if fd.get("bic"):
            teile.append(f"BIC: {fd['bic']}")
        if fd.get("geschaeftsfuehrung"):
            teile.append(f"Geschäftsführung: {fd['geschaeftsfuehrung']}")
        if fd.get("handelsregister"):
            teile.append(str(fd["handelsregister"]))
        if fd.get("ust_idnr"):
            teile.append(f"USt-IdNr.: {fd['ust_idnr']}")
        if len(teile) == 1:
            return
        self.set_y(-15)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(130, 130, 130)
        self.multi_cell(0, 3.5, " · ".join(teile), align="C")
        self.set_text_color(0, 0, 0)


def _adresse_zeilen(adresse: dict | None) -> list[str]:
    adresse = adresse or {}
    zeilen = []
    if adresse.get("strasse"):
        zeilen.append(str(adresse["strasse"]))
    ort = " ".join(str(adresse[k]) for k in ("plz", "ort") if adresse.get(k))
    if ort:
        zeilen.append(ort)
    return zeilen


def _angebot_adressbereich(pdf: FPDF, mandant: Mandant, kunde: Kunde) -> None:
    firmenadresse_zeilen = _adresse_zeilen(mandant.firmendaten.get("adresse") if mandant.firmendaten else None)

    # Kleine Ruecksendeangabe-Zeile oberhalb des Empfaenger-Blocks, wie auf
    # einem Fensterumschlag-Briefbogen.
    ruecksendeangabe = " · ".join([mandant.name, *firmenadresse_zeilen])
    pdf.set_xy(20, 38)
    pdf.set_font("Helvetica", "", 6)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 4, ruecksendeangabe)
    pdf.set_text_color(0, 0, 0)

    # Empfaenger links
    pdf.set_font("Helvetica", "", 10)
    for i, zeile in enumerate([kunde.name, *_adresse_zeilen(kunde.adresse)]):
        pdf.set_xy(20, 45 + i * 5)
        pdf.cell(85, 5, zeile)

    # Absender rechts
    fd = mandant.firmendaten or {}
    absender_zeilen = [mandant.name, *firmenadresse_zeilen]
    if fd.get("telefon"):
        absender_zeilen.append(f"Fon: {fd['telefon']}")
    absender_zeilen.append("")
    if fd.get("email"):
        absender_zeilen.append(str(fd["email"]))
    if fd.get("website"):
        absender_zeilen.append(str(fd["website"]))
    pdf.set_font("Helvetica", "", 9)
    for i, zeile in enumerate(absender_zeilen):
        pdf.set_xy(115, 45 + i * 5)
        pdf.cell(75, 5, zeile)


def _angebot_metadaten(pdf: FPDF, angebot: Angebot, kunde: Kunde, bearbeiter: User | None) -> None:
    pdf.set_xy(20, 85)
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 10, "Angebot")

    zeilen_links = [
        ("Angebots-Nr.:", angebot.angebotsnummer),
        ("Datum:", _fmt_datum(angebot.created_at)),
        ("Kunden-Nr.:", kunde.kundennummer),
    ]
    zeilen_rechts = [("Gültig bis:", _fmt_datum(angebot.gueltig_bis))]
    if bearbeiter:
        zeilen_rechts.append(("Bearbeiter:", bearbeiter.name))
        zeilen_rechts.append(("E-Mail:", bearbeiter.email))

    y = 103
    pdf.set_font("Helvetica", "B", 10)
    for i, (label, wert) in enumerate(zeilen_links):
        pdf.set_xy(20, y + i * 6)
        pdf.cell(32, 6, label)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(53, 6, wert)
        pdf.set_font("Helvetica", "B", 10)
    for i, (label, wert) in enumerate(zeilen_rechts):
        pdf.set_xy(115, y + i * 6)
        pdf.cell(30, 6, label)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(45, 6, wert)
        pdf.set_font("Helvetica", "B", 10)

    pdf.set_xy(20, y + max(len(zeilen_links), len(zeilen_rechts)) * 6 + 6)


def _angebot_positionen_tabelle(pdf: FPDF, positionen: list[AngebotPosition]) -> Decimal:
    spalten = (
        ("Pos.", 10),
        ("Art-Nr.", 22),
        ("Bezeichnung", 62),
        ("Menge", 16),
        ("Einheit", 16),
        ("Preis EUR", 22),
        ("Gesamt EUR", 22),
    )
    pdf.set_fill_color(235, 235, 235)
    pdf.set_font("Helvetica", "B", 9)
    for label, breite in spalten:
        pdf.cell(breite, 8, label, border=1, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    gesamt_netto = Decimal("0")
    for i, p in enumerate(sorted(positionen, key=lambda x: x.position)):
        zeilen_gesamt = p.menge * p.einzelpreis
        gesamt_netto += zeilen_gesamt
        pdf.set_fill_color(248, 248, 248)
        fill = i % 2 == 1
        pdf.cell(10, 7, str(p.position), border=1, fill=fill)
        pdf.cell(22, 7, p.artikelnummer or "", border=1, fill=fill)
        pdf.cell(62, 7, p.beschreibung[:38], border=1, fill=fill)
        pdf.cell(16, 7, f"{p.menge:g}", border=1, align="R", fill=fill)
        pdf.cell(16, 7, p.einheit, border=1, fill=fill)
        pdf.cell(22, 7, _fmt_betrag(p.einzelpreis), border=1, align="R", fill=fill)
        pdf.cell(22, 7, _fmt_betrag(zeilen_gesamt), border=1, align="R", fill=fill)
        pdf.ln()
    return gesamt_netto


def _angebot_summenblock(pdf: FPDF, gesamt_netto: Decimal, mwst_satz: Decimal) -> None:
    mwst_betrag = gesamt_netto * mwst_satz / Decimal("100")
    gesamt_brutto = gesamt_netto + mwst_betrag
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 10)
    for label, wert in (
        ("Summe Netto", _fmt_betrag(gesamt_netto)),
        (f"{_fmt_zahl(mwst_satz)}% USt. auf {_fmt_zahl(gesamt_netto)}", _fmt_betrag(mwst_betrag)),
    ):
        pdf.cell(90, 7, "", border=0)
        pdf.cell(58, 7, label)
        pdf.cell(22, 7, wert, align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_xy(110, pdf.get_y())
    pdf.line(110, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(1)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(90, 8, "", border=0)
    pdf.cell(58, 8, "Endsumme")
    pdf.cell(22, 8, _fmt_betrag(gesamt_brutto), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def generate_angebot_pdf(
    mandant: Mandant,
    angebot: Angebot,
    positionen: list[AngebotPosition],
    kunde: Kunde,
    bearbeiter: User | None = None,
    logo_bytes: bytes | None = None,
) -> bytes:
    pdf = _AngebotPDF(mandant, angebot, logo_bytes)
    pdf.set_margins(20, 15, 20)
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.add_page()

    _angebot_adressbereich(pdf, mandant, kunde)
    _angebot_metadaten(pdf, angebot, kunde, bearbeiter)
    pdf.ln(4)

    gesamt_netto = _angebot_positionen_tabelle(pdf, positionen)
    _angebot_summenblock(pdf, gesamt_netto, angebot.mwst_satz)
    return bytes(pdf.output())


def generate_rechnung_pdf(
    mandant: Mandant,
    rechnung: Rechnung,
    kunde: Kunde,
    positionen: list[RechnungPosition] | None = None,
    storniert_rechnung: Rechnung | None = None,
    *,
    pdfa_output_intent: bool = False,
) -> bytes:
    """pdfa_output_intent=True fuegt einen sRGB-OutputIntent hinzu (Betriebs-
    system fpdf2, kein "enforce_compliance"-Modus -- der wuerde ungebettete
    Core-Fonts wie Helvetica verbieten, die dieses Layout bewusst weiter
    nutzt). Wird ausschliesslich von e_invoice_service.baue_hybrid_pdf()
    gebraucht: drafthorse.pdf.attach_xml() liest vorhandene OutputIntents aus
    dem Quell-PDF aus und uebernimmt sie unveraendert in das ZUGFeRD-Hybrid-
    PDF, erzeugt aber selbst keinen -- ohne diesen Aufruf bliebe das Hybrid-
    PDF ohne ICC-Profil und damit nicht wirklich PDF/A-3-konform."""
    pdf = FPDF()
    pdf.add_page()
    titel = "Stornorechnung" if rechnung.ist_storno else "Rechnung"
    _kopf(pdf, mandant, titel, rechnung.rechnungsnummer, kunde)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Rechnungsdatum: {_fmt_datum(rechnung.created_at)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if rechnung.leistungsdatum:
        pdf.cell(0, 6, f"Leistungsdatum: {_fmt_datum(rechnung.leistungsdatum)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if rechnung.faellig_am:
        pdf.cell(0, 6, f"Faellig am: {_fmt_datum(rechnung.faellig_am)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if storniert_rechnung is not None:
        pdf.cell(
            0,
            6,
            f"Diese Stornorechnung storniert Rechnung {storniert_rechnung.rechnungsnummer} "
            f"vom {_fmt_datum(storniert_rechnung.created_at)}.",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
    pdf.ln(4)

    if positionen:
        gesamt_netto = _positionen_tabelle(pdf, positionen)
    else:
        gesamt_netto = rechnung.betrag_netto

    if (mandant.firmendaten or {}).get("ist_kleinunternehmer"):
        _summenblock_kleinunternehmer(pdf, gesamt_netto)
    else:
        _summenblock(pdf, gesamt_netto, rechnung.mwst_satz)

    if pdfa_output_intent:
        pdf.add_output_intent(
            OutputIntentSubType.PDFA,
            output_condition_identifier="sRGB",
            output_condition="IEC 61966-2-1:1999",
            registry_name="http://www.color.org",
            dest_output_profile=PDFICCProfile(
                contents=builtin_srgb2014_bytes(), n=3, alternate="DeviceRGB"
            ),
            info="sRGB2014 (v2)",
        )
    return bytes(pdf.output())


_MAHNSTUFEN_LABEL = {1: "1. Mahnung", 2: "2. Mahnung", 3: "3. Mahnung"}


def generate_mahnung_pdf(
    mandant: Mandant,
    rechnung: Rechnung,
    kunde: Kunde,
    mahnstufe: int,
    tage_ueberfaellig: int,
    betrag_brutto: Decimal,
    verzugszinsen: Decimal,
    mahnpauschale: Decimal,
) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    _kopf(pdf, mandant, _MAHNSTUFEN_LABEL.get(mahnstufe, "Mahnung"), rechnung.rechnungsnummer, kunde)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        6,
        f"Rechnung {rechnung.rechnungsnummer} vom {_fmt_datum(rechnung.created_at)}, "
        f"{tage_ueberfaellig} Tage ueberfaellig.",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(4)

    zeilen = [("Offener Rechnungsbetrag", betrag_brutto), ("Verzugszinsen (§ 288 BGB)", verzugszinsen)]
    if mahnpauschale:
        zeilen.append(("Mahnpauschale (§ 288 Abs. 5 BGB)", mahnpauschale))
    pdf.set_font("Helvetica", "", 10)
    for label, wert in zeilen:
        pdf.cell(148, 7, "", border=0)
        pdf.cell(22, 7, label)
        pdf.cell(22, 7, _fmt_betrag(wert), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    gesamt = betrag_brutto + verzugszinsen + mahnpauschale
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(148, 8, "", border=0)
    pdf.cell(22, 8, "Gesamt fällig")
    pdf.cell(22, 8, _fmt_betrag(gesamt), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return bytes(pdf.output())


def generate_maengel_protokoll_pdf(mandant: Mandant, vorgang: Vorgang, maengel: list[Mangel]) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, mandant.name, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Maengel-Protokoll: {vorgang.vorgangsnummer} - {vorgang.titel}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 10)
    spalten = (("Gemeldet am", 30), ("Schweregrad", 25), ("Status", 28), ("Beschreibung", 107))
    for label, breite in spalten:
        pdf.cell(breite, 8, label, border=1)
    pdf.ln()

    pdf.set_font("Helvetica", "", 10)
    for m in sorted(maengel, key=lambda x: x.created_at):
        pdf.cell(30, 8, _fmt_datum(m.created_at), border=1)
        pdf.cell(25, 8, m.schweregrad, border=1)
        pdf.cell(28, 8, m.status, border=1)
        pdf.cell(107, 8, m.beschreibung[:70], border=1)
        pdf.ln()

    if not maengel:
        pdf.cell(0, 8, "Keine Maengel erfasst.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    return bytes(pdf.output())


def generate_wochenzettel_pdf(
    mandant: Mandant,
    techniker: User,
    woche_start: date,
    woche_ende: date,
    eintraege: list[tuple[Zeiterfassung, Vorgang | None]],
) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, mandant.name, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        6,
        f"Wochenzettel: {techniker.name} ({_fmt_datum(woche_start)} - {_fmt_datum(woche_ende)})",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 10)
    spalten = (("Datum", 25), ("Vorgang", 30), ("Tätigkeit", 75), ("Von", 20), ("Bis", 20), ("Dauer", 20))
    for label, breite in spalten:
        pdf.cell(breite, 8, label, border=1)
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    gesamt_sekunden = 0.0
    for eintrag, vorgang in sorted(eintraege, key=lambda x: x[0].start_at):
        dauer_sekunden = (
            ((eintrag.ende_at - eintrag.start_at).total_seconds()) if eintrag.ende_at else 0.0
        )
        gesamt_sekunden += dauer_sekunden
        pdf.cell(25, 8, _fmt_datum(eintrag.start_at), border=1)
        vorgang_spalte = (
            vorgang.vorgangsnummer
            if vorgang
            else ZEITERFASSUNG_KATEGORIE_LABEL.get(eintrag.kategorie, "-")
        )
        pdf.cell(30, 8, vorgang_spalte, border=1)
        pdf.cell(75, 8, (eintrag.taetigkeit or "-")[:45], border=1)
        pdf.cell(20, 8, eintrag.start_at.strftime("%H:%M"), border=1, align="R")
        pdf.cell(
            20,
            8,
            eintrag.ende_at.strftime("%H:%M") if eintrag.ende_at else "läuft",
            border=1,
            align="R",
        )
        pdf.cell(20, 8, f"{dauer_sekunden / 3600:.2f} h", border=1, align="R")
        pdf.ln()

    if not eintraege:
        pdf.cell(0, 8, "Keine Zeiterfassungen in diesem Zeitraum.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, f"Gesamt: {gesamt_sekunden / 3600:.2f} Stunden", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    return bytes(pdf.output())


def generate_bestellung_pdf(
    mandant: Mandant, bestellung: Bestellung, positionen: list[BestellungPosition], lieferant: Lieferant | None
) -> bytes:
    """Anders als Angebot/Rechnung ist der Empfänger hier ein Lieferant statt
    ein Kunde -- eigener, schlankerer Kopf statt _kopf() (kein
    MwSt.-/Summenblock, da einzelpreis hier nur ein interner Richtwert ist,
    nicht der tatsaechliche Einkaufspreis des Lieferanten)."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, mandant.name, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Bestellung {bestellung.bestellnummer}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "Lieferant", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, lieferant.name if lieferant else "-", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if lieferant and lieferant.email:
        pdf.cell(0, 6, lieferant.email, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Datum: {_fmt_datum(bestellung.created_at)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    gesamt_netto = _positionen_tabelle(pdf, positionen)
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(148, 8, "", border=0)
    pdf.cell(22, 8, "Richtwert")
    pdf.cell(22, 8, _fmt_betrag(gesamt_netto), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    if bestellung.notiz:
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, "Notiz", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, bestellung.notiz)

    return bytes(pdf.output())


def _formular_antwort_text(feld: dict, antwort: object) -> str:
    if antwort is None or antwort == "":
        return "-"
    if feld["feld_typ"] == "ja_nein":
        return "Ja" if antwort else "Nein"
    if feld["feld_typ"] == "mehrfachauswahl" and isinstance(antwort, list):
        return _pdf_safe_text(", ".join(str(v) for v in antwort) or "-")
    return _pdf_safe_text(antwort)


def generate_formular_pdf(
    mandant: Mandant,
    vorgang: Vorgang,
    vorgang_formular: VorgangFormular,
    bilder: dict[str, bytes],
) -> bytes:
    """bilder enthaelt die heruntergeladenen Rohbytes je Foto-/
    Unterschrift-Feld (feld_id -> Bilddaten) -- der Route-Handler laedt
    diese vorher async aus dem Storage, da diese Funktion selbst
    synchron laeuft (siehe app/api/routes/vorgang_formulare.py).
    snapshot_version unterscheidet drei historisch gewachsene Layout-
    Formate (siehe formular_service.snapshot_von): 3 = freie Positionierung
    auf expliziten A4-Seiten (aktuell, wie MS-Access-Formular-Designer),
    2 = 12-Spalten-Raster mit automatischem Seitenumbruch, kein Feld/fehlend
    = urspruenglicher Flow-Renderer. Aeltere, bereits abgeschlossene
    Ausfuellungen laufen immer ueber den zu ihrer Version passenden
    Renderer, damit einmal ausgestellte PDFs bit-identisch reproduzierbar
    bleiben -- neue Snapshots werden nur noch in Version 3 erzeugt."""
    snapshot = vorgang_formular.formular_snapshot
    version = snapshot.get("snapshot_version")
    if version == 3:
        return _generate_formular_pdf_freeform(mandant, vorgang, vorgang_formular, bilder)
    if version == 2:
        return _generate_formular_pdf_raster(mandant, vorgang, vorgang_formular, bilder)
    return _generate_formular_pdf_legacy(mandant, vorgang, vorgang_formular, bilder)


def _generate_formular_pdf_legacy(
    mandant: Mandant,
    vorgang: Vorgang,
    vorgang_formular: VorgangFormular,
    bilder: dict[str, bytes],
) -> bytes:
    snapshot = vorgang_formular.formular_snapshot
    antworten = vorgang_formular.antworten

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, _pdf_safe_text(mandant.name), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        6,
        _pdf_safe_text(f"{snapshot.get('name', 'Formular')}: {vorgang.vorgangsnummer} - {vorgang.titel}"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.cell(
        0,
        6,
        f"Ausgefuellt am {_fmt_datum(vorgang_formular.abgeschlossen_am or vorgang_formular.created_at)}",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(6)

    for feld in sorted(snapshot.get("felder", []), key=lambda f: f["reihenfolge"]):
        if feld["feld_typ"] == "abschnitt":
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 8, _pdf_safe_text(feld["label"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
            continue

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, _pdf_safe_text(feld["label"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 10)

        antwort = antworten.get(feld["id"])
        if feld["feld_typ"] in ("foto", "unterschrift"):
            bild = bilder.get(feld["id"])
            if bild:
                try:
                    pdf.image(BytesIO(bild), h=40)
                except RuntimeError:
                    pdf.cell(0, 6, "[Bild konnte nicht eingebettet werden]", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            else:
                pdf.cell(0, 6, "-", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.multi_cell(0, 6, _formular_antwort_text(feld, antwort))
        pdf.ln(2)

    if not snapshot.get("felder"):
        pdf.cell(0, 8, "Keine Felder in diesem Formular.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    return bytes(pdf.output())


_FORMULAR_RAND_LR = 15
_FORMULAR_RAND_OBEN_FOLGESEITE = 22
_FORMULAR_RAND_UNTEN = 15


class _FormularPDF(FPDF):
    """Eigene Subklasse fuer die positionsbasierten Renderer (snapshot_
    version 2 = Raster, 3 = freie Positionierung) -- Seite 1 traegt den
    vollen Kopf (Mandant/Formularname/Vorgang/Datum) als normalen Flow-Text
    (siehe _generate_formular_pdf_raster/_generate_formular_pdf_freeform),
    Folgeseiten nur eine schmale Kennzeile, analog zum Muster in
    _AngebotPDF."""

    def __init__(self, mandant: Mandant, formular_name: str, vorgangsnummer: str):
        super().__init__()
        self._mandant = mandant
        self._formular_name = formular_name
        self._vorgangsnummer = vorgangsnummer
        self.set_margins(_FORMULAR_RAND_LR, 15, _FORMULAR_RAND_LR)

    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_xy(_FORMULAR_RAND_LR, 12)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(120, 120, 120)
        self.cell(
            0,
            6,
            _pdf_safe_text(
                f"{self._mandant.name} · {self._formular_name} · {self._vorgangsnummer} · Seite {self.page_no()}"
            ),
        )
        self.set_text_color(0, 0, 0)


def _formular_spaltenbreite_mm(pdf: FPDF) -> float:
    nutzbare_breite = pdf.w - pdf.l_margin - pdf.r_margin
    return nutzbare_breite / GRID_SPALTEN


def _render_formular_feld_zelle(
    pdf: FPDF,
    feld: dict,
    antwort: object,
    bild: bytes | None,
    x: float,
    y: float,
    breite: float,
    hoehe: float,
) -> None:
    if feld["feld_typ"] == "abschnitt":
        pdf.set_xy(x, y + hoehe / 2 - 3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(breite, 6, _pdf_safe_text(feld["label"]))
        pdf.line(x, y + hoehe - 1, x + breite, y + hoehe - 1)
        return

    label_hoehe = min(4.0, hoehe / 2)
    pdf.set_xy(x, y)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(110, 110, 110)
    pdf.cell(breite, label_hoehe, _pdf_safe_text(feld["label"]))
    pdf.set_text_color(0, 0, 0)

    wert_y = y + label_hoehe
    wert_hoehe = max(hoehe - label_hoehe, 3.0)
    if feld["feld_typ"] in ("foto", "unterschrift"):
        if bild:
            try:
                pdf.image(BytesIO(bild), x=x, y=wert_y, w=breite, h=wert_hoehe)
            except RuntimeError:
                pdf.set_xy(x, wert_y)
                pdf.set_font("Helvetica", "", 9)
                pdf.cell(breite, wert_hoehe, "[Bild konnte nicht eingebettet werden]")
        else:
            pdf.set_xy(x, wert_y)
            pdf.set_font("Helvetica", "", 9)
            pdf.cell(breite, wert_hoehe, "-")
        return

    pdf.set_xy(x, wert_y)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(breite, min(wert_hoehe, 5.0), _formular_antwort_text(feld, antwort))


def _generate_formular_pdf_raster(
    mandant: Mandant,
    vorgang: Vorgang,
    vorgang_formular: VorgangFormular,
    bilder: dict[str, bytes],
) -> bytes:
    snapshot = vorgang_formular.formular_snapshot
    antworten = vorgang_formular.antworten
    formular_name = snapshot.get("name", "Formular")
    zeilenhoehe_mm = snapshot.get("zeilenhoehe_mm", 8)
    felder = sorted(snapshot.get("felder", []), key=lambda f: (f["raster_zeile"], f["raster_spalte"]))

    pdf = _FormularPDF(mandant, formular_name, vorgang.vorgangsnummer)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, _pdf_safe_text(mandant.name), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        6,
        _pdf_safe_text(f"{formular_name}: {vorgang.vorgangsnummer} - {vorgang.titel}"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.cell(
        0,
        6,
        f"Ausgefuellt am {_fmt_datum(vorgang_formular.abgeschlossen_am or vorgang_formular.created_at)}",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(4)

    if not felder:
        pdf.cell(0, 8, "Keine Felder in diesem Formular.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        return bytes(pdf.output())

    spaltenbreite_mm = _formular_spaltenbreite_mm(pdf)
    raster_start_y = pdf.get_y()
    seite_start_zeile = 0

    def zeilen_kapazitaet(start_y: float) -> int:
        verfuegbar = pdf.h - pdf.b_margin - start_y
        return max(int(verfuegbar // zeilenhoehe_mm), 1)

    kapazitaet = zeilen_kapazitaet(raster_start_y)

    for feld in felder:
        lokale_zeile = feld["raster_zeile"] - seite_start_zeile
        if lokale_zeile + feld["raster_hoehe"] > kapazitaet:
            # Feld wuerde ueber die Seitengrenze ragen -- komplett auf die
            # naechste Seite verschieben statt anzuschneiden (siehe Docstring
            # von generate_formular_pdf).
            pdf.add_page()
            seite_start_zeile = feld["raster_zeile"]
            raster_start_y = _FORMULAR_RAND_OBEN_FOLGESEITE
            kapazitaet = zeilen_kapazitaet(raster_start_y)
            lokale_zeile = 0

        x = pdf.l_margin + feld["raster_spalte"] * spaltenbreite_mm
        y = raster_start_y + lokale_zeile * zeilenhoehe_mm
        breite = feld["raster_breite"] * spaltenbreite_mm
        hoehe = feld["raster_hoehe"] * zeilenhoehe_mm
        antwort = antworten.get(feld["id"])
        bild = bilder.get(feld["id"]) if feld["feld_typ"] in ("foto", "unterschrift") else None
        _render_formular_feld_zelle(pdf, feld, antwort, bild, x, y, breite, hoehe)

    return bytes(pdf.output())


def _generate_formular_pdf_freeform(
    mandant: Mandant,
    vorgang: Vorgang,
    vorgang_formular: VorgangFormular,
    bilder: dict[str, bytes],
) -> bytes:
    """snapshot_version 3 -- jede Seite ist eine feste A4-Flaeche, auf der
    Felder frei per x_mm/y_mm/breite_mm/hoehe_mm positioniert sind (wie
    Steuerelemente im MS-Access-Formular-Designer). Die Seitenaufteilung
    legt der Nutzer im Canvas-Editor explizit fest ("Seite hinzufuegen",
    siehe Formular.anzahl_seiten) -- anders als beim aelteren Raster-
    Renderer gibt es hier keinen automatischen Seitenumbruch und keine
    Sonderbehandlung fuer Felder, die ueber den Seitenrand ragen wuerden:
    das liegt vollstaendig in der Verantwortung des Nutzers."""
    snapshot = vorgang_formular.formular_snapshot
    antworten = vorgang_formular.antworten
    formular_name = snapshot.get("name", "Formular")
    anzahl_seiten = snapshot.get("anzahl_seiten", 1)
    felder_je_seite: dict[int, list[dict]] = {}
    for feld in snapshot.get("felder", []):
        felder_je_seite.setdefault(feld["seite"], []).append(feld)

    pdf = _FormularPDF(mandant, formular_name, vorgang.vorgangsnummer)

    for seite_idx in range(anzahl_seiten):
        pdf.add_page()
        if seite_idx == 0:
            pdf.set_font("Helvetica", "B", 18)
            pdf.cell(0, 10, _pdf_safe_text(mandant.name), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(
                0,
                6,
                _pdf_safe_text(f"{formular_name}: {vorgang.vorgangsnummer} - {vorgang.titel}"),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
            pdf.cell(
                0,
                6,
                f"Ausgefuellt am {_fmt_datum(vorgang_formular.abgeschlossen_am or vorgang_formular.created_at)}",
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
            pdf.ln(4)
            seiten_top_mm = pdf.get_y()
        else:
            seiten_top_mm = _FORMULAR_RAND_OBEN_FOLGESEITE

        for feld in sorted(felder_je_seite.get(seite_idx, []), key=lambda f: (f["y_mm"], f["x_mm"])):
            x = pdf.l_margin + feld["x_mm"]
            y = seiten_top_mm + feld["y_mm"]
            antwort = antworten.get(feld["id"])
            bild = bilder.get(feld["id"]) if feld["feld_typ"] in ("foto", "unterschrift") else None
            _render_formular_feld_zelle(pdf, feld, antwort, bild, x, y, feld["breite_mm"], feld["hoehe_mm"])

    if not snapshot.get("felder"):
        pdf.cell(0, 8, "Keine Felder in diesem Formular.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    return bytes(pdf.output())
