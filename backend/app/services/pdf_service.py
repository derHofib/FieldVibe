from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from uuid import UUID

from fpdf import FPDF
from fpdf.enums import OutputIntentSubType, XPos, YPos
from fpdf.output import PDFICCProfile
from fpdf.util import builtin_srgb2014_bytes

from app.models.angebot import Angebot, AngebotPosition
from app.models.bestellung import Bestellung, BestellungPosition
from app.models.form_modul import FormField, FormGroup, FormPresentationElement, FormSubmission, FormViewFieldLayout
from app.models.kunde import Kunde
from app.models.lieferant import Lieferant
from app.models.mandant import Mandant
from app.models.mangel import Mangel
from app.models.rechnung import Rechnung, RechnungPosition
from app.models.user import User
from app.models.vorgang import Vorgang
from app.models.zeiterfassung import Zeiterfassung
from app.schemas.zeiterfassung import ZEITERFASSUNG_KATEGORIE_LABEL

# fpdf2s core fonts (Helvetica/Times/Courier) sind standardmaessig Latin-1-
# kodiert -- das deckt Umlaute/ß ab, aber NICHT das Euro-Zeichen. Rechnung und
# Angebot (_BelegPDF) stellen deshalb auf cp1252 um und schreiben "€". Mahnung/
# Bestellung nutzen weiter die Standardkodierung und damit "EUR" statt "€",
# was eine Custom-Font-Einbettung spart, ohne dass Betraege missverstaendlich
# waeren.
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


_POSITIONEN_SPALTEN = (("Pos.", 12), ("Beschreibung", 90), ("Menge", 22), ("Einheit", 22), ("Preis", 22), ("Gesamt", 22))
_POSITIONEN_BREITE = sum(breite for _, breite in _POSITIONEN_SPALTEN)


def _positionen_kopfzeile(pdf: FPDF) -> None:
    pdf.set_font("Helvetica", "B", 10)
    for label, breite in _POSITIONEN_SPALTEN:
        pdf.cell(breite, 8, label, border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 10)


def _positionszeile(pdf: FPDF, p: AngebotPosition) -> Decimal:
    zeilen_gesamt = p.menge * p.einzelpreis
    pdf.cell(12, 8, str(p.position), border=1)
    pdf.cell(90, 8, _pdf_safe_text(p.beschreibung)[:55], border=1)
    pdf.cell(22, 8, f"{p.menge:g}", border=1, align="R")
    pdf.cell(22, 8, _pdf_safe_text(p.einheit), border=1)
    pdf.cell(22, 8, _fmt_betrag(p.einzelpreis), border=1, align="R")
    pdf.cell(22, 8, _fmt_betrag(zeilen_gesamt), border=1, align="R")
    pdf.ln()
    return zeilen_gesamt


def _positionen_tabelle(pdf: FPDF, positionen: list[AngebotPosition]) -> Decimal:
    _positionen_kopfzeile(pdf)
    gesamt_netto = Decimal("0")
    for p in sorted(positionen, key=lambda x: x.position):
        gesamt_netto += _positionszeile(pdf, p)
    return gesamt_netto


def _adresse_zeilen(adresse: dict | None) -> list[str]:
    adresse = adresse or {}
    zeilen = []
    if adresse.get("strasse"):
        zeilen.append(str(adresse["strasse"]))
    ort = " ".join(str(adresse[k]) for k in ("plz", "ort") if adresse.get(k))
    if ort:
        zeilen.append(ort)
    return zeilen


# --- Rechnung + Angebot: gemeinsames ruhiges Beleg-Layout ---------------------
# Ohne Tabellenrahmen/Fuellungen; Rechnung und Angebot unterscheiden sich nur
# in Belegart, Info-Paaren, Texten und Endbetrag-Label.

_TEXT = (30, 30, 30)
_GRAU = (120, 120, 120)
_LINIE_HELL = (225, 225, 225)
_LINIE_KOPF = (200, 200, 200)
_AKZENT = (10, 106, 209)

_CENT = Decimal("0.01")
_SEITE_TOP_FOLGE = 25
_B_SPALTEN = (10, 84, 26, 25, 25)
_B_X_POS = 20
_B_X_BESCHR = _B_X_POS + _B_SPALTEN[0]
_B_X_MENGE = _B_X_BESCHR + _B_SPALTEN[1]
_B_X_EP = _B_X_MENGE + _B_SPALTEN[2]
_B_X_GESAMT = _B_X_EP + _B_SPALTEN[3]
_B_X_ENDE = _B_X_GESAMT + _B_SPALTEN[4]
_B_PAD = 2.5
_B_ZEILE = 4.6
_B_ARTNR_ZEILE = 4.0
_B_ZWISCHENSUMME_HOEHE = 8.0
# DIN 5008 Form B: das Anschriftfeld endet bei ~90 mm, der Titel darf nie
# hineinragen.
_B_TITEL_MIN_Y = 90.0
_B_TITEL_ABSTAND = 10.0


def _fmt_euro(betrag: Decimal) -> str:
    return f"{_fmt_zahl(betrag)} €"


def _fmt_menge(menge: Decimal) -> str:
    s = f"{menge:f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s.replace(".", ",")


def _set_grau(pdf: FPDF) -> None:
    pdf.set_text_color(*_GRAU)


def _set_text(pdf: FPDF) -> None:
    pdf.set_text_color(*_TEXT)


class _BelegPDF(FPDF):
    """Gemeinsame Basis fuer Rechnung und Angebot: Logo/Kennzeile im Kopf,
    Firmen- und Bankdaten im Fuss jeder Seite (dort auch "Seite n von N",
    daher alias_nb_pages)."""

    def __init__(self, mandant: Mandant, belegart: str, nummer: str, logo_bytes: bytes | None):
        super().__init__()
        # Core-Fonts kodieren sonst latin-1 und kennen "€" nicht; cp1252
        # (WinAnsi) enthaelt es und ist in jedem Viewer verfuegbar.
        self.core_fonts_encoding = "cp1252"
        self._mandant = mandant
        self._belegart = belegart
        self._nummer = nummer
        self._logo_bytes = logo_bytes
        self.alias_nb_pages()

    def header(self) -> None:
        if self.page_no() == 1:
            logo_ok = False
            if self._logo_bytes:
                try:
                    self.image(BytesIO(self._logo_bytes), x=20, y=15, h=16)
                    logo_ok = True
                except Exception:
                    # Defektes Logo darf den Beleg nicht verhindern.
                    logo_ok = False
            if not logo_ok:
                self.set_xy(20, 15)
                self.set_font("Helvetica", "B", 18)
                self.set_text_color(60, 60, 60)
                self.cell(0, 10, _pdf_safe_text(self._mandant.name))
        else:
            self.set_xy(20, 12)
            self.set_font("Helvetica", "", 8)
            _set_grau(self)
            self.cell(
                0,
                5,
                _pdf_safe_text(
                    f"{self._mandant.name} · {self._belegart} {self._nummer} · Seite {self.page_no()}"
                ),
            )
        _set_text(self)

    def footer(self) -> None:
        fd = self._mandant.firmendaten or {}
        spalte_a = [self._mandant.name, *_adresse_zeilen(fd.get("adresse"))]
        spalte_b = []
        if fd.get("telefon"):
            spalte_b.append(f"Tel.: {fd['telefon']}")
        if fd.get("email"):
            spalte_b.append(str(fd["email"]))
        if fd.get("website"):
            spalte_b.append(str(fd["website"]))
        if fd.get("steuernummer"):
            spalte_b.append(f"Steuernummer: {fd['steuernummer']}")
        if fd.get("ust_idnr"):
            spalte_b.append(f"USt-IdNr.: {fd['ust_idnr']}")
        if fd.get("geschaeftsfuehrung"):
            spalte_b.append(f"Geschäftsführung: {fd['geschaeftsfuehrung']}")
        if fd.get("handelsregister"):
            spalte_b.append(str(fd["handelsregister"]))
        spalte_c = []
        if fd.get("bank_name"):
            spalte_c.append(str(fd["bank_name"]))
        if fd.get("iban"):
            spalte_c.append(f"IBAN: {fd['iban']}")
        if fd.get("bic"):
            spalte_c.append(f"BIC: {fd['bic']}")

        y0 = self.h - 30
        self.set_draw_color(*_LINIE_HELL)
        self.set_line_width(0.2)
        self.line(20, y0, 190, y0)
        self.set_font("Helvetica", "", 7)
        _set_grau(self)
        for x, breite, zeilen in ((20, 55, spalte_a), (78, 55, spalte_b), (136, 54, spalte_c)):
            self.set_xy(x, y0 + 2)
            if zeilen:
                self.multi_cell(breite, 3.2, _pdf_safe_text("\n".join(zeilen)))
        self.set_xy(150, self.h - 9)
        self.cell(40, 3.5, f"Seite {self.page_no()} von {{nb}}", align="R")
        _set_text(self)


def _beleg_adressbereich(
    pdf: FPDF, mandant: Mandant, kunde: Kunde, paare: list[tuple[str, str]]
) -> float:
    """DIN 5008 Form B: Ruecksendezeile ab 45 mm, Anschriftfeld ab 50 mm,
    Info-Block rechts. Gibt das untere Ende des tieferen Blocks zurueck."""
    fd = mandant.firmendaten or {}
    pdf.set_xy(20, 45)
    pdf.set_font("Helvetica", "", 6)
    _set_grau(pdf)
    pdf.cell(85, 4, _pdf_safe_text(" · ".join([mandant.name, *_adresse_zeilen(fd.get("adresse"))])))

    _set_text(pdf)
    pdf.set_font("Helvetica", "", 10)
    empfaenger = [kunde.name, *_adresse_zeilen(kunde.adresse)][:6]
    for i, zeile in enumerate(empfaenger):
        pdf.set_xy(20, 50 + i * 5)
        pdf.cell(85, 5, _pdf_safe_text(zeile))
    ende_empfaenger = 50 + len(empfaenger) * 5

    wert_breite = 38
    # Bis 7 mm ueber den Textrand hinaus toleriert, bevor die Schrift schrumpft.
    wert_max = wert_breite + 7
    for i, (label, wert) in enumerate(paare):
        y = 50 + i * 5.5
        pdf.set_xy(125, y)
        pdf.set_font("Helvetica", "", 8)
        _set_grau(pdf)
        pdf.cell(27, 5, _pdf_safe_text(label))
        text = _pdf_safe_text(wert)
        # Lange Werte (z. B. E-Mail-Adressen) schrumpfen statt in den Rand
        # zu laufen.
        groesse = 9.0
        pdf.set_font("Helvetica", "", groesse)
        while groesse > 6.5 and pdf.get_string_width(text) > wert_max:
            groesse -= 0.5
            pdf.set_font("Helvetica", "", groesse)
        _set_text(pdf)
        pdf.cell(wert_breite, 5, text)
    ende_info = 50 + (len(paare) - 1) * 5.5 + 5 if paare else 0
    return max(ende_empfaenger, ende_info)


def _beleg_titelbereich(
    pdf: FPDF,
    y: float,
    titel: str,
    nummer: str,
    zusatzzeile: str | None,
    einleitung: str,
) -> None:
    pdf.set_xy(20, y)
    pdf.set_font("Helvetica", "B", 20)
    _set_text(pdf)
    pdf.cell(0, 9, titel, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 9)
    _set_grau(pdf)
    pdf.cell(0, 5, _pdf_safe_text(f"Nr. {nummer}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if zusatzzeile:
        pdf.cell(0, 5, _pdf_safe_text(zusatzzeile), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)
    pdf.set_font("Helvetica", "", 10)
    _set_text(pdf)
    pdf.cell(0, 5, _pdf_safe_text(einleitung), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(8)


def _linie(pdf: FPDF, y: float, farbe: tuple[int, int, int], x1: float = 20, x2: float = 190) -> None:
    pdf.set_draw_color(*farbe)
    pdf.set_line_width(0.2)
    pdf.line(x1, y, x2, y)


def _b_kopfzeile(pdf: FPDF) -> None:
    y = pdf.get_y()
    pdf.set_font("Helvetica", "", 7.5)
    _set_grau(pdf)
    for x, breite, label, align in (
        (_B_X_POS, _B_SPALTEN[0], "POS.", "L"),
        (_B_X_BESCHR, _B_SPALTEN[1], "BESCHREIBUNG", "L"),
        (_B_X_MENGE, _B_SPALTEN[2], "MENGE", "R"),
        (_B_X_EP, _B_SPALTEN[3], "EINZELPREIS", "R"),
        (_B_X_GESAMT, _B_SPALTEN[4], "GESAMT", "R"),
    ):
        pdf.set_xy(x, y)
        pdf.cell(breite, 5, label, align=align)
    _linie(pdf, y + 6.5, _LINIE_KOPF)
    pdf.set_y(y + 7)
    _set_text(pdf)


def _b_platz(pdf: FPDF, hoehe: float) -> bool:
    return pdf.get_y() + hoehe <= pdf.page_break_trigger


def _b_neue_seite(pdf: FPDF, mit_kopfzeile: bool = True) -> None:
    pdf.add_page()
    pdf.set_y(_SEITE_TOP_FOLGE)
    if mit_kopfzeile:
        _b_kopfzeile(pdf)


def _b_beschreibung_zeilen(pdf: FPDF, p: AngebotPosition | RechnungPosition) -> list[str]:
    pdf.set_font("Helvetica", "", 9.5)
    return pdf.multi_cell(
        _B_SPALTEN[1], _B_ZEILE, _pdf_safe_text(p.beschreibung), dry_run=True, output="LINES"
    ) or [""]


def _b_artikelnummer(p: AngebotPosition | RechnungPosition) -> str | None:
    # Nur AngebotPosition kennt eine Artikelnummer.
    return _pdf_safe_text(getattr(p, "artikelnummer", None)).strip() or None


def _b_positionshoehe(pdf: FPDF, p: AngebotPosition | RechnungPosition) -> float:
    hoehe = 2 * _B_PAD + len(_b_beschreibung_zeilen(pdf, p)) * _B_ZEILE
    if _b_artikelnummer(p):
        hoehe += _B_ARTNR_ZEILE
    return hoehe


def _b_position(pdf: FPDF, p: AngebotPosition | RechnungPosition, mit_linie: bool) -> Decimal:
    """Zeichnet die Position ohne Seitenumbruch-Pruefung (macht der Aufrufer
    ueber _b_positionshoehe), damit eine Position nie geteilt wird."""
    zeilen = _b_beschreibung_zeilen(pdf, p)
    hoehe = _b_positionshoehe(pdf, p)
    y0 = pdf.get_y()
    yt = y0 + _B_PAD
    gesamt = p.menge * p.einzelpreis

    pdf.set_font("Helvetica", "", 9)
    _set_grau(pdf)
    pdf.set_xy(_B_X_POS, yt)
    pdf.cell(_B_SPALTEN[0], _B_ZEILE, str(p.position))

    pdf.set_font("Helvetica", "", 9.5)
    _set_text(pdf)
    for i, zeile in enumerate(zeilen):
        pdf.set_xy(_B_X_BESCHR, yt + i * _B_ZEILE)
        pdf.cell(_B_SPALTEN[1], _B_ZEILE, zeile)

    artikelnummer = _b_artikelnummer(p)
    if artikelnummer:
        pdf.set_font("Helvetica", "", 8)
        _set_grau(pdf)
        pdf.set_xy(_B_X_BESCHR, yt + len(zeilen) * _B_ZEILE)
        pdf.cell(_B_SPALTEN[1], _B_ARTNR_ZEILE, f"Art.-Nr. {artikelnummer}")
        _set_text(pdf)

    einheit = _pdf_safe_text(p.einheit or "").strip()
    menge = f"{_fmt_menge(p.menge)} {einheit}".strip()
    pdf.set_font("Helvetica", "", 9)
    for x, breite, text in (
        (_B_X_MENGE, _B_SPALTEN[2], menge),
        (_B_X_EP, _B_SPALTEN[3], _fmt_euro(p.einzelpreis)),
        (_B_X_GESAMT, _B_SPALTEN[4], _fmt_euro(gesamt)),
    ):
        pdf.set_xy(x, yt)
        pdf.cell(breite, _B_ZEILE, text, align="R")

    pdf.set_y(y0 + hoehe)
    if mit_linie:
        _linie(pdf, y0 + hoehe, _LINIE_HELL)
    return gesamt


def _b_zwischensumme(pdf: FPDF, betrag: Decimal) -> None:
    y = pdf.get_y() + 1.5
    pdf.set_font("Helvetica", "", 9)
    _set_grau(pdf)
    pdf.set_xy(_B_X_MENGE, y)
    pdf.cell(_B_SPALTEN[2] + _B_SPALTEN[3], 5, "Zwischensumme", align="R")
    pdf.set_xy(_B_X_GESAMT, y)
    pdf.cell(_B_SPALTEN[4], 5, _fmt_euro(betrag), align="R")
    pdf.set_y(y + 5)
    _set_text(pdf)


def _beleg_positionen(
    pdf: FPDF,
    positionen: list[AngebotPosition] | list[RechnungPosition],
    vorgang_koepfe: dict[UUID, tuple[str, str]],
    hoehe_nach_letzter: float,
) -> Decimal:
    """Positionen ohne Vorgang zuerst, danach je Vorgang Gruppenkopf, Positionen
    und Zwischensumme (nur Rechnung hat Vorgangs-Gruppen). Zwischen den
    Positionen nur eine feine Trennlinie. hoehe_nach_letzter ist der Platz,
    den Summenblock + Abschluss direkt unter der letzten Position brauchen:
    passt er nicht mehr, wandert die letzte Position mit auf die neue Seite,
    damit der Summenblock nie allein steht."""
    sortiert = sorted(positionen, key=lambda x: x.position)
    ohne_vorgang = [p for p in sortiert if getattr(p, "vorgang_id", None) is None]
    gruppen: dict[UUID, list] = {}
    for p in sortiert:
        vorgang_id = getattr(p, "vorgang_id", None)
        if vorgang_id is not None:
            gruppen.setdefault(vorgang_id, []).append(p)

    bloecke: list[tuple[list, str | None]] = []
    if ohne_vorgang:
        bloecke.append((ohne_vorgang, None))
    for vorgang_id, gruppe in gruppen.items():
        nummer, titel = vorgang_koepfe.get(vorgang_id, ("Vorgang", ""))
        bloecke.append((gruppe, f"{nummer} · {titel}" if titel else nummer))

    _b_kopfzeile(pdf)
    gesamt_netto = Decimal("0")

    for block_idx, (liste, gruppenkopf) in enumerate(bloecke):
        summe = Decimal("0")
        kopf_hoehe = 0.0
        kopf_zeilen: list[str] = []
        if gruppenkopf is not None:
            pdf.set_font("Helvetica", "B", 10)
            kopf_zeilen = pdf.multi_cell(
                _B_X_ENDE - _B_X_POS, 5, _pdf_safe_text(gruppenkopf), dry_run=True, output="LINES"
            )
            kopf_hoehe = 5.0 + len(kopf_zeilen) * 5 + 1.5
        for i, p in enumerate(liste):
            letzte = i == len(liste) - 1
            gesamt_letzte = letzte and block_idx == len(bloecke) - 1
            hoehe = _b_positionshoehe(pdf, p)
            # Gruppenkopf + erste Position und letzte Position + Zwischensumme
            # bleiben jeweils zusammen auf einer Seite.
            noetig = hoehe
            if i == 0:
                noetig += kopf_hoehe
            if letzte and gruppenkopf is not None:
                noetig += _B_ZWISCHENSUMME_HOEHE
            if gesamt_letzte:
                noetig += hoehe_nach_letzter
            if not _b_platz(pdf, noetig):
                _b_neue_seite(pdf)
                spacing = False
            else:
                spacing = True
            if i == 0 and gruppenkopf is not None:
                if spacing:
                    pdf.set_y(pdf.get_y() + 5)
                pdf.set_font("Helvetica", "B", 10)
                _set_text(pdf)
                for zeile in kopf_zeilen:
                    pdf.set_x(_B_X_POS)
                    pdf.cell(_B_X_ENDE - _B_X_POS, 5, zeile, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_y(pdf.get_y() + 1.5)
            summe += _b_position(pdf, p, mit_linie=not letzte)
        if gruppenkopf is not None:
            _b_zwischensumme(pdf, summe.quantize(_CENT))
        gesamt_netto += summe
    return gesamt_netto


def _beleg_summenblock_hoehe(kleinunternehmer: bool) -> float:
    # 6 Abstand + (Netto/USt-Zeilen + Linie) + Endbetrag (+ §19-Hinweis)
    return 6 + (8 + 5 if kleinunternehmer else 6 * 2 + 3 + 8)


def _beleg_summenblock(
    pdf: FPDF,
    gesamt_netto: Decimal,
    mwst_satz: Decimal,
    kleinunternehmer: bool,
    endbetrag_label: str,
    *,
    label_akzent: bool = False,
    hoehe_danach: float = 0.0,
) -> None:
    netto = gesamt_netto.quantize(_CENT)
    hoehe = _beleg_summenblock_hoehe(kleinunternehmer) + hoehe_danach
    if not _b_platz(pdf, hoehe):
        _b_neue_seite(pdf, mit_kopfzeile=False)
    pdf.set_y(pdf.get_y() + 6)
    x = 115
    if kleinunternehmer:
        brutto = netto
    else:
        mwst = (netto * mwst_satz / Decimal("100")).quantize(_CENT)
        brutto = netto + mwst
        satz = f"{mwst_satz:f}"
        if "." in satz:
            satz = satz.rstrip("0").rstrip(".")
        pdf.set_font("Helvetica", "", 9)
        _set_text(pdf)
        for label, wert in (
            ("Summe netto", _fmt_euro(netto)),
            (f"zzgl. {satz.replace('.', ',')} % USt.", _fmt_euro(mwst)),
        ):
            y = pdf.get_y()
            pdf.set_xy(x, y)
            pdf.cell(40, 6, _pdf_safe_text(label))
            pdf.set_xy(155, y)
            pdf.cell(35, 6, wert, align="R")
            pdf.set_y(y + 6)
        _linie(pdf, pdf.get_y() + 1, _LINIE_KOPF, x1=x, x2=190)
        pdf.set_y(pdf.get_y() + 3)
    y = pdf.get_y()
    pdf.set_font("Helvetica", "B", 12)
    if label_akzent:
        pdf.set_text_color(*_AKZENT)
    else:
        _set_text(pdf)
    pdf.set_xy(x, y)
    pdf.cell(40, 8, endbetrag_label)
    pdf.set_text_color(*_AKZENT)
    pdf.set_xy(155, y)
    pdf.cell(35, 8, _fmt_euro(brutto), align="R")
    _set_text(pdf)
    pdf.set_y(y + 8)
    if kleinunternehmer:
        pdf.set_font("Helvetica", "", 8)
        _set_grau(pdf)
        pdf.set_xy(x, pdf.get_y() + 1)
        pdf.cell(75, 4, "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.")
        pdf.set_y(pdf.get_y() + 4)
        _set_text(pdf)


def _beleg_abschluss_zeilen(pdf: FPDF, absaetze: list[str]) -> list[list[str]]:
    pdf.set_font("Helvetica", "", 9)
    return [
        pdf.multi_cell(170, 4.6, _pdf_safe_text(a), dry_run=True, output="LINES") for a in absaetze
    ]


def _beleg_abschluss_hoehe(pdf: FPDF, absaetze: list[str]) -> float:
    zeilen = _beleg_abschluss_zeilen(pdf, absaetze)
    # je Absatz 8 Abstand + Zeilen, danach 8 Abstand + Gruss + Firmenname
    return sum(8 + len(z) * 4.6 for z in zeilen) + 8 + 10


def _beleg_abschluss(pdf: FPDF, mandant: Mandant, absaetze: list[str]) -> None:
    hoehe = _beleg_abschluss_hoehe(pdf, absaetze)
    if not _b_platz(pdf, hoehe):
        _b_neue_seite(pdf, mit_kopfzeile=False)
    pdf.set_x(20)
    pdf.set_font("Helvetica", "", 9)
    _set_text(pdf)
    for absatz in absaetze:
        pdf.set_y(pdf.get_y() + 8)
        pdf.set_x(20)
        pdf.multi_cell(170, 4.6, _pdf_safe_text(absatz), align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_y(pdf.get_y() + 8)
    pdf.set_x(20)
    pdf.cell(0, 5, "Mit freundlichen Grüßen", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 5, _pdf_safe_text(mandant.name), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _beleg_rumpf(
    pdf: _BelegPDF,
    mandant: Mandant,
    kunde: Kunde,
    *,
    paare: list[tuple[str, str]],
    titel: str,
    nummer: str,
    zusatzzeile: str | None,
    einleitung: str,
    positionen: list[AngebotPosition] | list[RechnungPosition] | None,
    vorgang_koepfe: dict[UUID, tuple[str, str]],
    netto_ohne_positionen: Decimal,
    mwst_satz: Decimal,
    endbetrag_label: str,
    label_akzent: bool,
    absaetze: list[str],
) -> None:
    pdf.set_margins(20, 15, 20)
    pdf.set_auto_page_break(auto=True, margin=30)
    pdf.add_page()
    _set_text(pdf)

    ende_adressen = _beleg_adressbereich(pdf, mandant, kunde, paare)
    titel_y = max(_B_TITEL_MIN_Y, ende_adressen + _B_TITEL_ABSTAND)
    _beleg_titelbereich(pdf, titel_y, titel, nummer, zusatzzeile, einleitung)

    kleinunternehmer = bool((mandant.firmendaten or {}).get("ist_kleinunternehmer"))
    abschluss_hoehe = _beleg_abschluss_hoehe(pdf, absaetze)
    if positionen:
        gesamt_netto = _beleg_positionen(
            pdf,
            positionen,
            vorgang_koepfe,
            _beleg_summenblock_hoehe(kleinunternehmer) + abschluss_hoehe,
        )
    else:
        gesamt_netto = netto_ohne_positionen
    _beleg_summenblock(
        pdf,
        gesamt_netto,
        mwst_satz,
        kleinunternehmer,
        endbetrag_label,
        label_akzent=label_akzent,
        hoehe_danach=abschluss_hoehe,
    )
    _beleg_abschluss(pdf, mandant, absaetze)


def generate_angebot_pdf(
    mandant: Mandant,
    angebot: Angebot,
    positionen: list[AngebotPosition],
    kunde: Kunde,
    bearbeiter: User | None = None,
    logo_bytes: bytes | None = None,
) -> bytes:
    paare = [
        ("Angebotsnummer", angebot.angebotsnummer),
        ("Datum", _fmt_datum(angebot.created_at)),
        ("Kundennummer", kunde.kundennummer),
    ]
    if angebot.gueltig_bis:
        paare.append(("Gültig bis", _fmt_datum(angebot.gueltig_bis)))
    if bearbeiter:
        paare.append(("Ansprechpartner", bearbeiter.name))
        paare.append(("E-Mail", bearbeiter.email))
    schluss = ["Wir freuen uns auf Ihren Auftrag."]
    if angebot.gueltig_bis:
        schluss.insert(0, f"Dieses Angebot ist gültig bis {_fmt_datum(angebot.gueltig_bis)}.")
    absaetze = ["\n".join(schluss)]

    pdf = _BelegPDF(mandant, "Angebot", angebot.angebotsnummer, logo_bytes)
    _beleg_rumpf(
        pdf,
        mandant,
        kunde,
        paare=paare,
        titel="Angebot",
        nummer=angebot.angebotsnummer,
        zusatzzeile=None,
        einleitung="Vielen Dank für Ihre Anfrage. Gerne bieten wir Ihnen folgende Leistungen an:",
        positionen=positionen,
        vorgang_koepfe={},
        netto_ohne_positionen=Decimal("0"),
        mwst_satz=angebot.mwst_satz,
        endbetrag_label="Angebotssumme",
        label_akzent=True,
        absaetze=absaetze,
    )
    return bytes(pdf.output())


def generate_rechnung_pdf(
    mandant: Mandant,
    rechnung: Rechnung,
    kunde: Kunde,
    positionen: list[RechnungPosition] | None = None,
    storniert_rechnung: Rechnung | None = None,
    *,
    vorgang_koepfe: dict[UUID, tuple[str, str]] | None = None,
    pdfa_output_intent: bool = False,
    logo_bytes: bytes | None = None,
) -> bytes:
    """pdfa_output_intent=True fuegt einen sRGB-OutputIntent hinzu (Betriebs-
    system fpdf2, kein "enforce_compliance"-Modus -- der wuerde ungebettete
    Core-Fonts wie Helvetica verbieten, die dieses Layout bewusst weiter
    nutzt). Wird ausschliesslich von e_invoice_service.baue_hybrid_pdf()
    gebraucht: drafthorse.pdf.attach_xml() liest vorhandene OutputIntents aus
    dem Quell-PDF aus und uebernimmt sie unveraendert in das ZUGFeRD-Hybrid-
    PDF, erzeugt aber selbst keinen -- ohne diesen Aufruf bliebe das Hybrid-
    PDF ohne ICC-Profil und damit nicht wirklich PDF/A-3-konform."""
    fd = mandant.firmendaten or {}
    storno = rechnung.ist_storno
    titel = "Stornorechnung" if storno else "Rechnung"

    paare = [
        ("Rechnungsnummer", rechnung.rechnungsnummer),
        ("Rechnungsdatum", _fmt_datum(rechnung.created_at)),
        # §14 Abs. 4 Nr. 6 UStG verlangt den Leistungszeitpunkt immer -- ohne
        # eigenes Leistungsdatum gilt das Rechnungsdatum und wird so ausgewiesen.
        ("Leistungsdatum", _fmt_datum(rechnung.leistungsdatum or rechnung.created_at)),
        ("Kundennummer", kunde.kundennummer),
    ]
    if rechnung.faellig_am:
        paare.append(("Fällig am", _fmt_datum(rechnung.faellig_am)))
    if kunde.ust_idnr:
        paare.append(("USt-IdNr. Kunde", kunde.ust_idnr))

    zusatzzeile = None
    if storniert_rechnung is not None:
        zusatzzeile = (
            f"Storniert Rechnung {storniert_rechnung.rechnungsnummer} "
            f"vom {_fmt_datum(storniert_rechnung.created_at)}."
        )

    absaetze = []
    if not storno and fd.get("iban"):
        if rechnung.faellig_am:
            absaetze.append(
                f"Bitte überweisen Sie den Rechnungsbetrag bis zum {_fmt_datum(rechnung.faellig_am)} "
                f"unter Angabe der Rechnungsnummer {rechnung.rechnungsnummer} auf das unten genannte Konto."
            )
        else:
            absaetze.append(
                f"Bitte überweisen Sie den Rechnungsbetrag unter Angabe der Rechnungsnummer "
                f"{rechnung.rechnungsnummer} auf das unten genannte Konto."
            )

    pdf = _BelegPDF(mandant, titel, rechnung.rechnungsnummer, logo_bytes)
    _beleg_rumpf(
        pdf,
        mandant,
        kunde,
        paare=paare,
        titel=titel,
        nummer=rechnung.rechnungsnummer,
        zusatzzeile=zusatzzeile,
        einleitung=(
            "Hiermit stornieren wir die oben genannte Rechnung vollständig."
            if storno
            else "Vielen Dank für Ihren Auftrag. Wir berechnen Ihnen folgende Leistungen:"
        ),
        positionen=positionen,
        vorgang_koepfe=vorgang_koepfe or {},
        netto_ohne_positionen=rechnung.betrag_netto,
        mwst_satz=rechnung.mwst_satz,
        endbetrag_label="Rechnungsbetrag",
        label_akzent=False,
        absaetze=absaetze,
    )

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
    spalten = (
        ("Datum", 25),
        ("Vorgang", 30),
        ("Tätigkeit", 60),
        ("Von", 20),
        ("Bis", 20),
        ("Dauer", 20),
        ("km", 15),
    )
    for label, breite in spalten:
        pdf.cell(breite, 8, label, border=1)
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    gesamt_sekunden = 0.0
    gesamt_km = Decimal("0")
    for eintrag, vorgang in sorted(eintraege, key=lambda x: x[0].start_at):
        dauer_sekunden = (
            ((eintrag.ende_at - eintrag.start_at).total_seconds()) if eintrag.ende_at else 0.0
        )
        gesamt_sekunden += dauer_sekunden
        if eintrag.km is not None:
            gesamt_km += eintrag.km
        pdf.cell(25, 8, _fmt_datum(eintrag.start_at), border=1)
        vorgang_spalte = (
            vorgang.vorgangsnummer
            if vorgang
            else ZEITERFASSUNG_KATEGORIE_LABEL.get(eintrag.kategorie, "-")
        )
        pdf.cell(30, 8, vorgang_spalte, border=1)
        pdf.cell(60, 8, (eintrag.taetigkeit or "-")[:36], border=1)
        pdf.cell(20, 8, eintrag.start_at.strftime("%H:%M"), border=1, align="R")
        pdf.cell(
            20,
            8,
            eintrag.ende_at.strftime("%H:%M") if eintrag.ende_at else "läuft",
            border=1,
            align="R",
        )
        pdf.cell(20, 8, f"{dauer_sekunden / 3600:.2f} h", border=1, align="R")
        pdf.cell(15, 8, f"{eintrag.km:.1f}" if eintrag.km is not None else "-", border=1, align="R")
        pdf.ln()

    if not eintraege:
        pdf.cell(0, 8, "Keine Zeiterfassungen in diesem Zeitraum.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    gesamt_text = f"Gesamt: {gesamt_sekunden / 3600:.2f} Stunden"
    if gesamt_km:
        gesamt_text += f" · {gesamt_km:.1f} km"
    pdf.cell(0, 8, gesamt_text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

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


def _formular_vorschau_banner(pdf: FPDF) -> None:
    """Auffaelliger Hinweis auf Seite 1, wenn das PDF vor dem Abschliessen
    der Ausfuellung erzeugt wird -- verhindert, dass eine Vorschau mit
    noch unvollstaendigen/nicht gespeicherten Antworten mit dem finalen
    Dokument verwechselt wird."""
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(255, 244, 214)
    pdf.set_text_color(153, 105, 0)
    pdf.cell(
        0, 7, "VORSCHAU -- Formular noch nicht abgeschlossen", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True
    )
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 10)
    pdf.ln(2)


_FORMULAR_RAND_LR = 15
_FORMULAR_RAND_OBEN_FOLGESEITE = 22
_FORMULAR_RAND_UNTEN = 15


class _FormularPDF(FPDF):
    """Eigene Subklasse fuer den positionsbasierten Formular-Renderer
    (siehe generate_form_submission_pdf) -- Seite 1 traegt den vollen Kopf
    (Mandant/Schema-Name/Vorgang/Datum) als normalen Flow-Text,
    Folgeseiten nur eine schmale Kennzeile, analog zum Muster in
    _BelegPDF."""

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


def _form_antwort_text(field: FormField, wert: object) -> str:
    if wert is None or wert == "":
        return "-"
    if field.feld_typ == "ja_nein":
        return "Ja" if wert else "Nein"
    if field.feld_typ == "mehrfachauswahl" and isinstance(wert, list):
        return _pdf_safe_text(", ".join(str(v) for v in wert) or "-")
    if field.feld_typ == "datei" and isinstance(wert, dict):
        # Anders als foto/unterschrift wird eine Datei nie eingebettet
        # (kein Bild, ggf. PDF-in-PDF) -- nur der Dateiname als Hinweis,
        # dass etwas hochgeladen wurde.
        return _pdf_safe_text(wert.get("filename") or "Datei hochgeladen")
    if field.feld_typ == "foto_plan":
        # Nur fuer die fliessende Wiederholgruppen-Liste (siehe
        # generate_form_submission_pdf) -- die frei positionierte Seite
        # bettet das zusammengesetzte Bild ueber _render_form_feld_zelle
        # ein, hier reicht ein Text-Hinweis wie bei "datei".
        hat_foto = isinstance(wert, dict) and bool(wert.get("foto"))
        return "Foto hinterlegt" if hat_foto else "-"
    if field.feld_typ == "adresse" and isinstance(wert, dict):
        teile = [str(wert[k]) for k in ("strasse", "plz", "ort") if wert.get(k)]
        return _pdf_safe_text(", ".join(teile) or "-")
    return _pdf_safe_text(wert)


def _render_form_feld_zelle(
    pdf: FPDF, field: FormField, wert: object, bild: bytes | None, x: float, y: float, breite: float, hoehe: float
) -> None:
    label = field.label.get("de", field.key)
    label_hoehe = min(4.0, hoehe / 2)
    pdf.set_xy(x, y)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(110, 110, 110)
    pdf.cell(breite, label_hoehe, _pdf_safe_text(label))
    pdf.set_text_color(0, 0, 0)

    wert_y = y + label_hoehe
    wert_hoehe = max(hoehe - label_hoehe, 3.0)
    if field.feld_typ in ("foto", "unterschrift", "foto_plan"):
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
    pdf.multi_cell(breite, min(wert_hoehe, 5.0), _form_antwort_text(field, wert))


def generate_form_submission_pdf(
    mandant: Mandant,
    vorgang: Vorgang,
    submission: FormSubmission,
    schema_name: str,
    fields: list[FormField],
    groups: list[FormGroup],
    layouts: list[FormViewFieldLayout],
    elements: list[FormPresentationElement],
    bilder: dict[str, bytes],
    ist_vorschau: bool = False,
) -> bytes:
    """PDF fuer eine form_submission ueber eine print-View: Root-Felder frei
    positioniert nach x_mm/y_mm/breite_mm/hoehe_mm der form_view_field_
    layouts einer View (key-basiert, fields[].key statt einer UUID), keine
    eingefrorene Momentaufnahme -- die aktuelle Schema-Definition
    entscheidet, dieselbe Herangehensweise wie beim Rest von Formular-Modul
    v2 (siehe Docstring Migration 0076 -- "alte Versionen bleiben stehen
    statt dupliziert zu werden").

    Wiederholgruppen lassen sich nicht sinnvoll frei positionieren (eine
    unbekannte Anzahl Zeilen passt nicht auf feste x_mm/y_mm-Koordinaten)
    -- sie werden nach den frei positionierten Seiten als einfache
    fliessende Liste angehaengt, eine Seite pro Gruppe mit Eintraegen."""
    values = submission.values
    layouts_je_seite: dict[int, list[FormViewFieldLayout]] = {}
    for layout in layouts:
        layouts_je_seite.setdefault(layout.seite, []).append(layout)
    headings_je_seite: dict[int, list[FormPresentationElement]] = {}
    for element in elements:
        if element.type == "heading" and element.x_mm is not None and element.y_mm is not None:
            headings_je_seite.setdefault(element.seite, []).append(element)
    fields_by_key = {f.key: f for f in fields}
    anzahl_seiten = max([*layouts_je_seite.keys(), *headings_je_seite.keys(), 0]) + 1

    pdf = _FormularPDF(mandant, schema_name, vorgang.vorgangsnummer)

    for seite_idx in range(anzahl_seiten):
        pdf.add_page()
        if seite_idx == 0:
            pdf.set_font("Helvetica", "B", 18)
            pdf.cell(0, 10, _pdf_safe_text(mandant.name), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(
                0,
                6,
                _pdf_safe_text(f"{schema_name}: {vorgang.vorgangsnummer} - {vorgang.titel}"),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
            pdf.cell(
                0,
                6,
                f"Ausgefuellt am {_fmt_datum(submission.abgeschlossen_am or submission.created_at)}",
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
            pdf.ln(4)
            if ist_vorschau:
                _formular_vorschau_banner(pdf)
            seiten_top_mm = pdf.get_y()
        else:
            seiten_top_mm = _FORMULAR_RAND_OBEN_FOLGESEITE

        for element in sorted(headings_je_seite.get(seite_idx, []), key=lambda e: (e.y_mm or 0, e.x_mm or 0)):
            x = pdf.l_margin + (element.x_mm or 0)
            y = seiten_top_mm + (element.y_mm or 0)
            inhalt = element.inhalt.get("text", {})
            text = inhalt.get("de", "") if isinstance(inhalt, dict) else ""
            pdf.set_xy(x, y + (element.hoehe_mm or 8) / 2 - 3)
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(element.breite_mm or 85, 6, _pdf_safe_text(text))

        for layout in sorted(layouts_je_seite.get(seite_idx, []), key=lambda l: (l.y_mm, l.x_mm)):
            field = fields_by_key.get(layout.field_key)
            if field is None or field.group_key is not None:
                continue
            x = pdf.l_margin + layout.x_mm
            y = seiten_top_mm + layout.y_mm
            wert = values.get(field.key)
            bild = bilder.get(field.key) if field.feld_typ in ("foto", "unterschrift", "foto_plan") else None
            _render_form_feld_zelle(pdf, field, wert, bild, x, y, layout.breite_mm, layout.hoehe_mm)

    if not layouts and not headings_je_seite:
        pdf.cell(0, 8, "Keine Felder in diesem Formular.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    for group in groups:
        zeilen = values.get(group.key)
        if not isinstance(zeilen, list) or not zeilen:
            continue
        gruppen_felder = [f for f in fields if f.group_key == group.key]
        pdf.add_page()
        pdf.set_xy(pdf.l_margin, _FORMULAR_RAND_OBEN_FOLGESEITE)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, _pdf_safe_text(group.label.get("de", group.key)), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)
        # Abschnitt (repeatable=False): genau ein Block ohne "Eintrag
        # N"-Kennzeichnung -- fachlich kein Wiederholbereich, nur eine
        # Gruppierung von Feldern.
        for idx, zeile in enumerate(zeilen):
            if group.repeatable:
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(0, 6, f"Eintrag {idx + 1}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "", 9)
            for field in gruppen_felder:
                label = field.label.get("de", field.key)
                text = _form_antwort_text(field, zeile.get(field.key) if isinstance(zeile, dict) else None)
                pdf.multi_cell(0, 5, f"{label}: {text}")
            pdf.ln(2)
            if not group.repeatable:
                break

    return bytes(pdf.output())
