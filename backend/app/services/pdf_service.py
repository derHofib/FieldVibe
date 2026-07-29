from datetime import date, datetime
from decimal import Decimal

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.models.angebot import Angebot, AngebotPosition
from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.mangel import Mangel
from app.models.rechnung import Rechnung, RechnungPosition
from app.models.vorgang import Vorgang

# fpdf2s core fonts (Helvetica/Times/Courier) sind Windows-1252-kodiert --
# das deckt deutsche Umlaute/ß ab, aber NICHT das Euro-Zeichen zuverlaessig
# ueber alle Renderer hinweg. "EUR" statt "€" spart eine Custom-Font-
# Einbettung, ohne dass Betraege missverstaendlich waeren.
_WAEHRUNG = "EUR"


def _fmt_betrag(betrag: Decimal) -> str:
    return f"{betrag:,.2f} {_WAEHRUNG}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_datum(d: date | datetime | None) -> str:
    if d is None:
        return "-"
    return d.strftime("%d.%m.%Y")


def _kopf(pdf: FPDF, mandant: Mandant, titel: str, nummer: str, kunde: Kunde) -> None:
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, mandant.name, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
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


def generate_angebot_pdf(
    mandant: Mandant, angebot: Angebot, positionen: list[AngebotPosition], kunde: Kunde
) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    _kopf(pdf, mandant, "Angebot", angebot.angebotsnummer, kunde)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Datum: {_fmt_datum(angebot.created_at)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if angebot.gueltig_bis:
        pdf.cell(0, 6, f"Gueltig bis: {_fmt_datum(angebot.gueltig_bis)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    gesamt_netto = _positionen_tabelle(pdf, positionen)
    _summenblock(pdf, gesamt_netto, angebot.mwst_satz)
    return bytes(pdf.output())


def generate_rechnung_pdf(
    mandant: Mandant, rechnung: Rechnung, kunde: Kunde, positionen: list[RechnungPosition] | None = None
) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    _kopf(pdf, mandant, "Rechnung", rechnung.rechnungsnummer, kunde)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Rechnungsdatum: {_fmt_datum(rechnung.created_at)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if rechnung.faellig_am:
        pdf.cell(0, 6, f"Faellig am: {_fmt_datum(rechnung.faellig_am)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    if positionen:
        gesamt_netto = _positionen_tabelle(pdf, positionen)
    else:
        gesamt_netto = rechnung.betrag_netto
    _summenblock(pdf, gesamt_netto, rechnung.mwst_satz)
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
