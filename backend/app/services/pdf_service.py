import re
from datetime import date, datetime, timedelta
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


def _fmt_datum(d: date | datetime | None) -> str:
    if d is None:
        return "-"
    return d.strftime("%d.%m.%Y")


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


_INFO_X_LABEL = 125
_INFO_X_WERT = 152
_INFO_WERT_BREITE = 38
_INFO_ZEILE = 4.6


def _info_wert_zeilen(pdf: FPDF, text: str, breite: float) -> list[str]:
    """Bricht einen Info-Wert in Normalgroesse auf Zeilen <= breite um (Font
    muss bereits gesetzt sein). Bevorzugt Trennstellen nach "@", "." und
    Leerzeichen/Bindestrich, sonst zeichenweise -- so laeuft z. B. eine lange
    E-Mail-Adresse nie ueber den rechten Rand."""
    if pdf.get_string_width(text) <= breite:
        return [text]
    zeilen: list[str] = []
    aktuell = ""
    for teil in re.findall(r".*?[@.\s-]|.+$", text):
        while pdf.get_string_width(teil.rstrip()) > breite:
            # Einzelnes Token zu lang: Rest der laufenden Zeile abschliessen und
            # das Token zeichenweise zerlegen.
            if aktuell:
                zeilen.append(aktuell.rstrip())
                aktuell = ""
            n = len(teil)
            while n > 1 and pdf.get_string_width(teil[:n]) > breite:
                n -= 1
            zeilen.append(teil[:n])
            teil = teil[n:]
        if aktuell and pdf.get_string_width((aktuell + teil).rstrip()) > breite:
            zeilen.append(aktuell.rstrip())
            aktuell = ""
        aktuell += teil
    if aktuell.strip():
        zeilen.append(aktuell.rstrip())
    return zeilen or [text]


def _beleg_adressbereich(
    pdf: FPDF, mandant: Mandant, empfaenger: list[str], paare: list[tuple[str, str]]
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
    zeilen_empfaenger = empfaenger[:6]
    for i, zeile in enumerate(zeilen_empfaenger):
        pdf.set_xy(20, 50 + i * 5)
        pdf.cell(85, 5, _pdf_safe_text(zeile))
    ende_empfaenger = 50 + len(zeilen_empfaenger) * 5

    y = 50.0
    ende_info = 0.0
    for label, wert in paare:
        pdf.set_font("Helvetica", "", 9)
        wert_zeilen = _info_wert_zeilen(pdf, _pdf_safe_text(wert), _INFO_WERT_BREITE)
        pdf.set_xy(_INFO_X_LABEL, y)
        pdf.set_font("Helvetica", "", 8)
        _set_grau(pdf)
        pdf.cell(_INFO_X_WERT - _INFO_X_LABEL, 5, _pdf_safe_text(label))
        pdf.set_font("Helvetica", "", 9)
        _set_text(pdf)
        for i, zeile in enumerate(wert_zeilen):
            pdf.set_xy(_INFO_X_WERT, y + i * _INFO_ZEILE)
            pdf.cell(_INFO_WERT_BREITE, 5, zeile)
        hoehe = max(5.5, len(wert_zeilen) * _INFO_ZEILE + 0.9)
        ende_info = y + max(5.0, len(wert_zeilen) * _INFO_ZEILE + 0.4)
        y += hoehe
    return max(ende_empfaenger, ende_info)


def _beleg_titelbereich(
    pdf: FPDF,
    y: float,
    titel: str,
    untertitel: list[str],
    einleitung: str,
) -> None:
    pdf.set_xy(20, y)
    pdf.set_font("Helvetica", "B", 20)
    _set_text(pdf)
    pdf.cell(0, 9, titel, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 9)
    _set_grau(pdf)
    for zeile in untertitel:
        pdf.cell(0, 5, _pdf_safe_text(zeile), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)
    pdf.set_font("Helvetica", "", 10)
    _set_text(pdf)
    pdf.multi_cell(170, 5, _pdf_safe_text(einleitung), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
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
    nur_netto: bool = False,
    hinweis: str | None = None,
) -> None:
    """nur_netto: Endbetrag ohne USt.-Zeilen (Bestellung -- Richtwert netto),
    mit optionalem grauem hinweis darunter."""
    netto = gesamt_netto.quantize(_CENT)
    hoehe = _beleg_summenblock_hoehe(kleinunternehmer or nur_netto) + hoehe_danach
    if not _b_platz(pdf, hoehe):
        _b_neue_seite(pdf, mit_kopfzeile=False)
    pdf.set_y(pdf.get_y() + 6)
    x = 115
    if kleinunternehmer or nur_netto:
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
    elif nur_netto and hinweis:
        pdf.set_font("Helvetica", "", 8)
        _set_grau(pdf)
        pdf.set_xy(x, pdf.get_y() + 1)
        pdf.cell(75, 4, _pdf_safe_text(hinweis))
        pdf.set_y(pdf.get_y() + 4)
        _set_text(pdf)


def _mahn_aufstellung_hoehe(anzahl_zeilen: int) -> float:
    # 6 Abstand + Zeilen + Linie + Endzeile
    return 6 + anzahl_zeilen * 6 + 3 + 8


def _mahn_aufstellung(
    pdf: FPDF, zeilen: list[tuple[str, Decimal]], endbetrag_label: str, endbetrag: Decimal, hoehe_danach: float
) -> None:
    """Rechtsbuendige Aufstellung wie der Summenblock, nur eine Linie vor dem
    Endbetrag."""
    if not _b_platz(pdf, _mahn_aufstellung_hoehe(len(zeilen)) + hoehe_danach):
        _b_neue_seite(pdf, mit_kopfzeile=False)
    pdf.set_y(pdf.get_y() + 6)
    x = 105
    pdf.set_font("Helvetica", "", 9)
    _set_text(pdf)
    for label, wert in zeilen:
        y = pdf.get_y()
        pdf.set_xy(x, y)
        pdf.cell(55, 6, _pdf_safe_text(label))
        pdf.set_xy(155, y)
        pdf.cell(35, 6, _fmt_euro(wert), align="R")
        pdf.set_y(y + 6)
    _linie(pdf, pdf.get_y() + 1, _LINIE_KOPF, x1=x, x2=190)
    pdf.set_y(pdf.get_y() + 3)
    y = pdf.get_y()
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*_AKZENT)
    pdf.set_xy(x, y)
    pdf.cell(50, 8, endbetrag_label)
    pdf.set_xy(155, y)
    pdf.cell(35, 8, _fmt_euro(endbetrag), align="R")
    _set_text(pdf)
    pdf.set_y(y + 8)


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
    empfaenger: list[str],
    *,
    paare: list[tuple[str, str]],
    titel: str,
    untertitel: list[str],
    einleitung: str,
    positionen: list[AngebotPosition] | list[RechnungPosition] | list[BestellungPosition] | None,
    vorgang_koepfe: dict[UUID, tuple[str, str]],
    netto_ohne_positionen: Decimal,
    mwst_satz: Decimal,
    endbetrag_label: str,
    label_akzent: bool,
    absaetze: list[str],
    nur_netto: bool = False,
    netto_hinweis: str | None = None,
    aufstellung: tuple[list[tuple[str, Decimal]], Decimal] | None = None,
    ohne_summenblock: bool = False,
) -> None:
    """aufstellung=(Zeilen, Endbetrag) ersetzt den USt.-Summenblock durch die
    Mahn-Aufstellung; ohne_summenblock laesst den Block ganz weg."""
    pdf.set_margins(20, 15, 20)
    pdf.set_auto_page_break(auto=True, margin=30)
    pdf.add_page()
    _set_text(pdf)

    ende_adressen = _beleg_adressbereich(pdf, mandant, empfaenger, paare)
    titel_y = max(_B_TITEL_MIN_Y, ende_adressen + _B_TITEL_ABSTAND)
    _beleg_titelbereich(pdf, titel_y, titel, untertitel, einleitung)

    kleinunternehmer = bool((mandant.firmendaten or {}).get("ist_kleinunternehmer"))
    abschluss_hoehe = _beleg_abschluss_hoehe(pdf, absaetze)
    if aufstellung is not None:
        summen_hoehe = _mahn_aufstellung_hoehe(len(aufstellung[0]))
    elif ohne_summenblock:
        summen_hoehe = 0.0
    else:
        summen_hoehe = _beleg_summenblock_hoehe(kleinunternehmer or nur_netto)
    if positionen:
        gesamt_netto = _beleg_positionen(pdf, positionen, vorgang_koepfe, summen_hoehe + abschluss_hoehe)
    else:
        gesamt_netto = netto_ohne_positionen
    if aufstellung is not None:
        _mahn_aufstellung(pdf, aufstellung[0], endbetrag_label, aufstellung[1], abschluss_hoehe)
    elif not ohne_summenblock:
        _beleg_summenblock(
            pdf,
            gesamt_netto,
            mwst_satz,
            kleinunternehmer,
            endbetrag_label,
            label_akzent=label_akzent,
            hoehe_danach=abschluss_hoehe,
            nur_netto=nur_netto,
            hinweis=netto_hinweis,
        )
    _beleg_abschluss(pdf, mandant, absaetze)


def _kunde_empfaenger(kunde: Kunde) -> list[str]:
    return [kunde.name, *_adresse_zeilen(kunde.adresse)]


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
        _kunde_empfaenger(kunde),
        paare=paare,
        titel="Angebot",
        untertitel=[f"Nr. {angebot.angebotsnummer}"],
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
        _kunde_empfaenger(kunde),
        paare=paare,
        titel=titel,
        untertitel=[f"Nr. {rechnung.rechnungsnummer}", *([zusatzzeile] if zusatzzeile else [])],
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
_MAHNTEXT = {
    1: (
        "sicherlich ist Ihnen entgangen, dass die oben genannte Rechnung seit {tage} Tagen fällig ist. "
        "Wir bitten Sie, den offenen Betrag zu begleichen."
    ),
    2: (
        "leider konnten wir bis heute keinen Zahlungseingang zu der oben genannten Rechnung feststellen, "
        "die seit {tage} Tagen fällig ist. Bitte begleichen Sie den offenen Betrag umgehend."
    ),
    3: (
        "trotz unserer bisherigen Erinnerungen ist die oben genannte Rechnung seit {tage} Tagen unbezahlt. "
        "Wir fordern Sie letztmalig auf, den offenen Betrag umgehend zu begleichen."
    ),
}


def generate_mahnung_pdf(
    mandant: Mandant,
    rechnung: Rechnung,
    kunde: Kunde,
    mahnstufe: int,
    tage_ueberfaellig: int,
    betrag_brutto: Decimal,
    verzugszinsen: Decimal,
    mahnpauschale: Decimal,
    logo_bytes: bytes | None = None,
) -> bytes:
    fd = mandant.firmendaten or {}
    titel = _MAHNSTUFEN_LABEL.get(mahnstufe, "Mahnung")
    paare = [
        ("Datum", _fmt_datum(date.today())),
        ("Rechnungsnummer", rechnung.rechnungsnummer),
        ("Rechnungsdatum", _fmt_datum(rechnung.created_at)),
    ]
    if rechnung.faellig_am:
        paare.append(("Fällig seit", _fmt_datum(rechnung.faellig_am)))
    paare.append(("Kundennummer", kunde.kundennummer))

    text = _MAHNTEXT.get(mahnstufe, _MAHNTEXT[3]).format(tage=tage_ueberfaellig)
    zeilen = [("Offener Rechnungsbetrag", betrag_brutto), ("Verzugszinsen (§ 288 BGB)", verzugszinsen)]
    if mahnpauschale:
        zeilen.append(("Mahnpauschale (§ 288 Abs. 5 BGB)", mahnpauschale))
    gesamt = betrag_brutto + verzugszinsen + mahnpauschale

    schluss = []
    if fd.get("iban"):
        schluss.append(
            f"Bitte überweisen Sie den Betrag unter Angabe der Rechnungsnummer {rechnung.rechnungsnummer} "
            "auf das unten genannte Konto."
        )
    schluss.append("Sollten Sie die Zahlung bereits veranlasst haben, betrachten Sie dieses Schreiben bitte als gegenstandslos.")

    pdf = _BelegPDF(mandant, titel, rechnung.rechnungsnummer, logo_bytes)
    _beleg_rumpf(
        pdf,
        mandant,
        _kunde_empfaenger(kunde),
        paare=paare,
        titel=titel,
        untertitel=[f"zu Rechnung {rechnung.rechnungsnummer} vom {_fmt_datum(rechnung.created_at)}"],
        einleitung=f"Sehr geehrte Damen und Herren,\n\n{text}",
        positionen=None,
        vorgang_koepfe={},
        netto_ohne_positionen=Decimal("0"),
        mwst_satz=Decimal("0"),
        endbetrag_label="Gesamt fällig",
        label_akzent=True,
        absaetze=["\n".join(schluss)],
        aufstellung=(zeilen, gesamt),
    )
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
    mandant: Mandant,
    bestellung: Bestellung,
    positionen: list[BestellungPosition],
    lieferant: Lieferant | None,
    logo_bytes: bytes | None = None,
) -> bytes:
    """Empfaenger ist ein Lieferant statt eines Kunden. Der Summenblock weist
    nur den Netto-Richtwert aus (kein USt.-Block): einzelpreis ist hier ein
    interner Richtwert, nicht der tatsaechliche Einkaufspreis des Lieferanten."""
    empfaenger = ["-"]
    if lieferant:
        empfaenger = [lieferant.name, *[z for z in (lieferant.email, lieferant.telefon) if z]]
    paare = [
        ("Bestellnummer", bestellung.bestellnummer),
        ("Datum", _fmt_datum(bestellung.created_at)),
    ]
    if bestellung.liefertermin:
        paare.append(("Liefertermin", _fmt_datum(bestellung.liefertermin)))
    absaetze = []
    if bestellung.notiz:
        absaetze.append(f"Bemerkung:\n{bestellung.notiz}")
    absaetze.append("Bitte bestätigen Sie uns die Bestellung und den Liefertermin.")

    pdf = _BelegPDF(mandant, "Bestellung", bestellung.bestellnummer, logo_bytes)
    _beleg_rumpf(
        pdf,
        mandant,
        empfaenger,
        paare=paare,
        titel="Bestellung",
        untertitel=[f"Nr. {bestellung.bestellnummer}"],
        einleitung="Hiermit bestellen wir folgende Artikel:",
        positionen=positionen,
        vorgang_koepfe={},
        netto_ohne_positionen=Decimal("0"),
        mwst_satz=Decimal("0"),
        endbetrag_label="Bestellsumme",
        label_akzent=True,
        absaetze=absaetze,
        nur_netto=True,
        netto_hinweis="Richtwert, netto zzgl. USt.",
    )
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


# --- Zeitplan (Gantt) ---------------------------------------------------------
# Eigenes Querformat-Layout auf der _BelegPDF-Basis (Logo/Fonts/Farben); Kopf
# und Fuss sind fuer Querformat neu positioniert. Alle Masse in mm.

_ZP_RAND = 10.0
_ZP_SPALTE_LINKS = 62.0
_ZP_ZEILE = 7.0
_ZP_ZEILE_BASIS = 9.0
_ZP_KOPF_MONAT = 5.0
_ZP_KOPF_KW = 5.0
_ZP_KOPF_TAG = 4.0
_ZP_ROT = (220, 38, 38)
_ZP_ROT_DUNKEL = (153, 27, 27)
_ZP_VIOLETT = (124, 58, 237)
_ZP_VIOLETT_DUNKEL = (76, 29, 149)
_ZP_AKZENT_DUNKEL = (6, 64, 125)
_ZP_PHASE = (55, 65, 81)
_ZP_SCHATTEN = (190, 190, 190)
_ZP_WOCHENENDE = (244, 244, 245)
_ZP_RASTER = (232, 232, 235)
_ZP_HEUTE = (234, 120, 0)
_ZP_VERBINDUNG = (90, 90, 100)
_ZP_MONATE = ("Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez")
_ZP_MONATE_LANG = (
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)  # fmt: skip


class _ZeitplanPDF(_BelegPDF):
    def __init__(self, mandant: Mandant, projekt_name: str, logo_bytes: bytes | None):
        super().__init__(mandant, "Zeitplan", projekt_name, logo_bytes)
        self.set_auto_page_break(False)

    def header(self) -> None:
        if self.page_no() == 1:
            logo_ok = False
            if self._logo_bytes:
                try:
                    self.image(BytesIO(self._logo_bytes), x=_ZP_RAND, y=8, h=11)
                    logo_ok = True
                except Exception:
                    logo_ok = False
            if not logo_ok:
                self.set_xy(_ZP_RAND, 8)
                self.set_font("Helvetica", "B", 14)
                self.set_text_color(60, 60, 60)
                self.cell(0, 8, _pdf_safe_text(self._mandant.name))
        else:
            self.set_xy(_ZP_RAND, 7)
            self.set_font("Helvetica", "", 8)
            _set_grau(self)
            self.cell(
                0,
                5,
                _pdf_safe_text(f"{self._mandant.name} · Zeitplan {self._nummer} · Seite {self.page_no()}"),
            )
        _set_text(self)

    def footer(self) -> None:
        self.set_font("Helvetica", "", 7)
        _set_grau(self)
        self.set_xy(_ZP_RAND, self.h - 8)
        self.cell(self.w / 2, 3.5, _pdf_safe_text(self._mandant.name))
        self.set_xy(self.w - _ZP_RAND - 40, self.h - 8)
        self.cell(40, 3.5, f"Seite {self.page_no()} von {{nb}}", align="R")
        _set_text(self)


def _zp_kuerzen(pdf: FPDF, text: str, breite: float) -> str:
    """Kuerzt (Font gesetzt) auf `breite`; haengt "..." an."""
    text = _pdf_safe_text(text)
    if pdf.get_string_width(text) <= breite:
        return text
    while text and pdf.get_string_width(text + "...") > breite:
        text = text[:-1]
    return text.rstrip() + "..."


def _zp_zeilen(zeitplan) -> list:
    phasen = sorted((e for e in zeitplan.elemente if e.typ == "phase"), key=lambda e: e.plan_reihenfolge)
    phasen_ids = {p.id for p in phasen}
    rest = [e for e in zeitplan.elemente if e.typ != "phase"]
    zeilen: list = []
    for p in phasen:
        zeilen.append(p)
        zeilen.extend(sorted((e for e in rest if e.phase_id == p.id), key=lambda e: e.plan_reihenfolge))
    zeilen.extend(
        sorted((e for e in rest if e.phase_id not in phasen_ids), key=lambda e: e.plan_reihenfolge)
    )
    return zeilen


def _zp_pfeil(pdf: FPDF, x: float, y: float, richtung: int, farbe: tuple[int, int, int]) -> None:
    """Pfeilspitze an (x, y); richtung +1 = nach rechts zeigend, -1 = links."""
    pdf.set_fill_color(*farbe)
    pdf.polygon([(x, y), (x - 1.6 * richtung, y - 0.9), (x - 1.6 * richtung, y + 0.9)], style="F")


def _zp_linie_pfad(pdf: FPDF, punkte: list[tuple[float, float]], farbe: tuple[int, int, int]) -> None:
    pdf.set_draw_color(*farbe)
    pdf.set_line_width(0.2)
    for (x1, y1), (x2, y2) in zip(punkte, punkte[1:]):
        pdf.line(x1, y1, x2, y2)
    letzte_x, letzte_y = punkte[-1]
    vorletzte_x = punkte[-2][0]
    _zp_pfeil(pdf, letzte_x, letzte_y, 1 if letzte_x >= vorletzte_x else -1, farbe)


def generate_zeitplan_pdf(
    mandant: Mandant,
    projekt_name: str,
    zeitplan,
    *,
    basisplan_name: str | None = None,
    kritischer_pfad: bool = True,
    logo_bytes: bytes | None = None,
    heute: date | None = None,
) -> bytes:
    """Gantt-Zeitplan als PDF (Querformat). A4; bei so langen Zeitraeumen,
    dass eine Woche auf A4 unter ~5 mm schrumpfen wuerde, A3 -- bleibt es
    auch dort zu eng, wird entsprechend weiter gestaucht (KW-Beschriftung
    dann nur jede zweite Woche). Verbindungen werden nur gezeichnet, wenn
    beide Zeilen auf derselben Seite liegen. `zeitplan` ist ein ZeitplanRead."""
    heute = heute or date.today()
    zeilen = _zp_zeilen(zeitplan)
    mit_basis = basisplan_name is not None
    zeile_h = _ZP_ZEILE_BASIS if mit_basis else _ZP_ZEILE

    daten: list[date] = []
    for e in zeitplan.elemente:
        for d in (e.start_am, e.ende_am, e.basis_start_am, e.basis_ende_am):
            if d is not None:
                daten.append(d)
    if not daten:
        daten = [heute, heute + timedelta(days=27)]
    erster = min(daten)
    t0 = erster - timedelta(days=erster.weekday())
    letzter = max(daten)
    t1 = letzter + timedelta(days=6 - letzter.weekday())
    tage = (t1 - t0).days + 1
    wochen = tage // 7
    tagesraster = wochen <= 6

    a4_breite = 297 - 2 * _ZP_RAND - _ZP_SPALTE_LINKS
    if a4_breite / wochen >= 5:
        format_, seiten_w, seiten_h = "A4", 297.0, 210.0
    else:
        format_, seiten_w, seiten_h = "A3", 420.0, 297.0
    zeit_x0 = _ZP_RAND + _ZP_SPALTE_LINKS
    zeit_breite = seiten_w - 2 * _ZP_RAND - _ZP_SPALTE_LINKS
    dpt = zeit_breite / tage
    wochen_breite = dpt * 7

    kopf_h = _ZP_KOPF_MONAT + _ZP_KOPF_KW + (_ZP_KOPF_TAG if tagesraster else 0)
    unten = seiten_h - 14
    legende_h = 12.0

    def x_von(d: date) -> float:
        return zeit_x0 + (d - t0).days * dpt

    # Seiten-Aufteilung: Seite 1 hat den Titelblock, spaeter nur die Kennzeile.
    seiten: list[list] = [[]]
    y_start = [44.0, 16.0]
    y_ist = y_start[0] + kopf_h
    for zeile in zeilen:
        if y_ist + zeile_h > unten:
            seiten.append([])
            y_ist = y_start[1] + kopf_h
        seiten[-1].append(zeile)
        y_ist += zeile_h
    if y_ist + legende_h > unten:
        seiten.append([])

    pdf = _ZeitplanPDF(mandant, projekt_name, logo_bytes)

    def zeichne_kopf(y0: float, y_ende: float) -> None:
        """Monats-/KW-(Tages-)Kopf plus Raster und Wochenenden bis y_ende."""
        pdf.set_line_width(0.15)
        # Wochenenden
        pdf.set_fill_color(*_ZP_WOCHENENDE)
        for i in range(tage):
            if (t0 + timedelta(days=i)).weekday() >= 5:
                pdf.rect(zeit_x0 + i * dpt, y0 + kopf_h, dpt, y_ende - (y0 + kopf_h), style="F")
        # Monate
        pdf.set_font("Helvetica", "B", 7)
        i = 0
        while i < tage:
            tag = t0 + timedelta(days=i)
            j = i
            while j < tage and (t0 + timedelta(days=j)).month == tag.month:
                j += 1
            breite = (j - i) * dpt
            pdf.set_fill_color(236, 238, 242)
            pdf.set_draw_color(*_ZP_RASTER)
            pdf.rect(zeit_x0 + i * dpt, y0, breite, _ZP_KOPF_MONAT, style="DF")
            if breite >= 24:
                beschriftung = f"{_ZP_MONATE_LANG[tag.month - 1]} {tag.year}"
            elif breite >= 9:
                beschriftung = f"{_ZP_MONATE[tag.month - 1]} {str(tag.year)[2:]}"
            else:
                beschriftung = ""
            if beschriftung:
                _set_text(pdf)
                pdf.set_xy(zeit_x0 + i * dpt, y0)
                pdf.cell(breite, _ZP_KOPF_MONAT, _pdf_safe_text(beschriftung), align="C")
            i = j
        # Kalenderwochen
        pdf.set_font("Helvetica", "", 6.5)
        schritt = 1 if wochen_breite >= 5.5 else 2
        for w in range(wochen):
            x = zeit_x0 + w * wochen_breite
            kw = (t0 + timedelta(days=7 * w)).isocalendar()[1]
            pdf.set_draw_color(*_ZP_RASTER)
            pdf.set_fill_color(247, 248, 250)
            pdf.rect(x, y0 + _ZP_KOPF_MONAT, wochen_breite, _ZP_KOPF_KW, style="DF")
            if w % schritt == 0:
                _set_grau(pdf)
                pdf.set_xy(x, y0 + _ZP_KOPF_MONAT)
                pdf.cell(wochen_breite * schritt, _ZP_KOPF_KW, f"KW {kw}" if wochen_breite >= 9 else str(kw), align="C")
            pdf.line(x, y0 + kopf_h, x, y_ende)
        pdf.line(zeit_x0 + tage * dpt, y0 + kopf_h, zeit_x0 + tage * dpt, y_ende)
        if tagesraster:
            pdf.set_font("Helvetica", "", 6)
            for i in range(tage):
                tag = t0 + timedelta(days=i)
                x = zeit_x0 + i * dpt
                pdf.set_draw_color(*_ZP_RASTER)
                pdf.rect(x, y0 + _ZP_KOPF_MONAT + _ZP_KOPF_KW, dpt, _ZP_KOPF_TAG, style="D")
                _set_grau(pdf)
                pdf.set_xy(x, y0 + _ZP_KOPF_MONAT + _ZP_KOPF_KW)
                pdf.cell(dpt, _ZP_KOPF_TAG, str(tag.day), align="C")
                pdf.line(x, y0 + kopf_h, x, y_ende)
        # Linke Spaltenueberschrift
        pdf.set_font("Helvetica", "B", 7)
        _set_grau(pdf)
        pdf.set_xy(_ZP_RAND, y0 + kopf_h - 5)
        pdf.cell(_ZP_SPALTE_LINKS, 5, "Phase / Arbeitsschritt")
        pdf.set_draw_color(*_LINIE_KOPF)
        pdf.set_line_width(0.3)
        pdf.line(_ZP_RAND, y0 + kopf_h, seiten_w - _ZP_RAND, y0 + kopf_h)
        _set_text(pdf)

    def balken_rechteck(e, x1: float, x2: float, y: float, hoehe: float) -> None:
        kritisch = kritischer_pfad and e.kritisch
        if e.typ == "phase":
            pdf.set_fill_color(*_ZP_PHASE)
            pdf.rect(x1, y + hoehe * 0.3, x2 - x1, hoehe * 0.4, style="F")
            # kleine Enden wie bei klassischen Sammelbalken
            pdf.polygon([(x1, y + hoehe * 0.7), (x1 + 1.2, y + hoehe * 0.7), (x1, y + hoehe * 1.0)], style="F")
            pdf.polygon([(x2, y + hoehe * 0.7), (x2 - 1.2, y + hoehe * 0.7), (x2, y + hoehe * 1.0)], style="F")
            return
        fremd = e.partner is not None
        grund = _ZP_VIOLETT if fremd else _AKZENT
        dunkel = _ZP_VIOLETT_DUNKEL if fremd else _ZP_AKZENT_DUNKEL
        pdf.set_fill_color(*grund)
        pdf.rect(x1, y, x2 - x1, hoehe, style="F")
        if e.fortschritt > 0:
            pdf.set_fill_color(*dunkel)
            pdf.rect(x1, y, (x2 - x1) * min(e.fortschritt, 100) / 100, hoehe, style="F")
        if kritisch:
            pdf.set_draw_color(*_ZP_ROT)
            pdf.set_line_width(0.5)
            pdf.rect(x1, y, x2 - x1, hoehe, style="D")

    def raute(e, mitte_x: float, mitte_y: float, r: float) -> None:
        kritisch = kritischer_pfad and e.kritisch
        pdf.set_fill_color(*(_ZP_ROT if kritisch else (30, 30, 30)))
        pdf.polygon([(mitte_x, mitte_y - r), (mitte_x + r, mitte_y), (mitte_x, mitte_y + r), (mitte_x - r, mitte_y)], style="F")
        if e.bestellung is not None:
            pdf.set_fill_color(*(_ZP_ROT_DUNKEL if kritisch else (234, 120, 0)))
            pdf.rect(mitte_x + r + 0.6, mitte_y - 1.1, 2.2, 2.2, style="F")

    for seiten_nr, sicht in enumerate(seiten):
        pdf.add_page(orientation="L", format=format_)
        if seiten_nr == 0:
            pdf.set_xy(_ZP_RAND, 22)
            pdf.set_font("Helvetica", "B", 18)
            _set_text(pdf)
            pdf.cell(0, 9, "Zeitplan")
            pdf.set_xy(_ZP_RAND, 31)
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 6, _pdf_safe_text(projekt_name))
            pdf.set_font("Helvetica", "", 8)
            _set_grau(pdf)
            zusatz = [f"Stand: {_fmt_datum(heute)}"]
            if basisplan_name is not None:
                zusatz.append(f"Vergleich mit Basisplan: {basisplan_name}")
            pdf.set_xy(_ZP_RAND, 37.5)
            pdf.cell(0, 4, _pdf_safe_text(" · ".join(zusatz)))
            _set_text(pdf)
        kopf_y = y_start[0] if seiten_nr == 0 else y_start[1]
        y_ende = kopf_y + kopf_h + len(sicht) * zeile_h
        if not sicht:
            y_ende = kopf_y + kopf_h + (8 if not zeilen else 0)
        zeichne_kopf(kopf_y, y_ende)
        if not zeilen:
            pdf.set_font("Helvetica", "", 9)
            _set_grau(pdf)
            pdf.set_xy(_ZP_RAND, kopf_y + kopf_h + 2)
            pdf.cell(100, 5, "Der Zeitplan enthält noch keine Elemente.")
            _set_text(pdf)

        lage: dict = {}
        y = kopf_y + kopf_h
        for e in sicht:
            lage[e.id] = y
            # Zeilentrenner
            pdf.set_draw_color(*_ZP_RASTER)
            pdf.set_line_width(0.1)
            pdf.line(_ZP_RAND, y + zeile_h, seiten_w - _ZP_RAND, y + zeile_h)
            # Beschriftung links
            einzug = 0.0 if e.typ == "phase" else 3.5
            sub = []
            if e.start_am is not None and e.ende_am is not None:
                sub.append(
                    e.start_am.strftime("%d.%m.")
                    if e.start_am == e.ende_am
                    else f"{e.start_am.strftime('%d.%m.')}-{e.ende_am.strftime('%d.%m.')}"
                )
            else:
                sub.append("ohne Termin")
            if e.zugewiesen_name:
                sub.append(e.zugewiesen_name)
            if e.partner is not None:
                sub.append(e.partner.name)
            pdf.set_font("Helvetica", "B" if e.typ == "phase" else "", 7.5)
            _set_text(pdf)
            pdf.set_xy(_ZP_RAND + einzug, y + 0.7)
            pdf.cell(_ZP_SPALTE_LINKS - einzug - 1, 3.2, _zp_kuerzen(pdf, e.titel, _ZP_SPALTE_LINKS - einzug - 2))
            pdf.set_font("Helvetica", "", 5.8)
            _set_grau(pdf)
            pdf.set_xy(_ZP_RAND + einzug, y + 3.9)
            pdf.cell(
                _ZP_SPALTE_LINKS - einzug - 1,
                2.6,
                _zp_kuerzen(pdf, " · ".join(sub), _ZP_SPALTE_LINKS - einzug - 2),
            )
            _set_text(pdf)
            # Basisplan (Schattenbalken darunter)
            hoehe = 3.6 if not mit_basis else 3.4
            bar_y = y + (zeile_h - hoehe) / 2 - (1.0 if mit_basis else 0)
            if mit_basis and e.basis_start_am is not None and e.basis_ende_am is not None:
                pdf.set_fill_color(*_ZP_SCHATTEN)
                if e.typ == "meilenstein":
                    mx = x_von(e.basis_start_am) + dpt / 2
                    my = y + zeile_h - 1.6
                    pdf.polygon([(mx, my - 1.1), (mx + 1.1, my), (mx, my + 1.1), (mx - 1.1, my)], style="F")
                else:
                    pdf.rect(
                        x_von(e.basis_start_am), y + zeile_h - 2.6, x_von(e.basis_ende_am + timedelta(days=1)) - x_von(e.basis_start_am), 1.5, style="F"
                    )
            if e.start_am is None or e.ende_am is None:
                y += zeile_h
                continue
            x1, x2 = x_von(e.start_am), x_von(e.ende_am + timedelta(days=1))
            if e.typ == "meilenstein":
                raute(e, x1 + dpt / 2, bar_y + hoehe / 2, 2.0)
            else:
                balken_rechteck(e, x1, max(x2, x1 + 0.6), bar_y, hoehe)
            y += zeile_h

        # Heute-Linie
        if t0 <= heute <= t1:
            hx = x_von(heute) + dpt / 2
            pdf.set_draw_color(*_ZP_HEUTE)
            pdf.set_line_width(0.4)
            pdf.line(hx, kopf_y + kopf_h - 1, hx, y_ende)

        # Verbindungen (nur innerhalb der Seite)
        elemente_nach_id = {e.id: e for e in sicht}
        for a in zeitplan.abhaengigkeiten:
            v, n = elemente_nach_id.get(a.vorgaenger_id), elemente_nach_id.get(a.nachfolger_id)
            if v is None or n is None or None in (v.start_am, v.ende_am, n.start_am, n.ende_am):
                continue
            hoehe_v = 1.0 if mit_basis else 0.0
            yv = lage[v.id] + zeile_h / 2 - hoehe_v
            yn = lage[n.id] + zeile_h / 2 - hoehe_v

            def kante(e, seite: str) -> float:
                if e.typ == "meilenstein":
                    mitte = x_von(e.start_am) + dpt / 2
                    return mitte - 2.0 if seite == "links" else mitte + 2.0 + (2.8 if e.bestellung else 0)
                return x_von(e.start_am) if seite == "links" else x_von(e.ende_am + timedelta(days=1))

            farbe = _ZP_ROT if kritischer_pfad and a.kritisch else _ZP_VERBINDUNG
            if a.art == "ende_anfang":
                xv, xn = kante(v, "rechts"), kante(n, "links")
                if xn - 2 >= xv + 2:
                    punkte = [(xv, yv), (xv + 2, yv), (xv + 2, yn), (xn, yn)]
                else:
                    ymitte = lage[v.id] + zeile_h if yn > yv else lage[v.id]
                    punkte = [(xv, yv), (xv + 2, yv), (xv + 2, ymitte), (xn - 2, ymitte), (xn - 2, yn), (xn, yn)]
            elif a.art == "anfang_anfang":
                xv, xn = kante(v, "links"), kante(n, "links")
                x_l = min(xv, xn) - 2
                punkte = [(xv, yv), (x_l, yv), (x_l, yn), (xn, yn)]
            else:
                xv, xn = kante(v, "rechts"), kante(n, "rechts")
                x_l = max(xv, xn) + 2
                punkte = [(xv, yv), (x_l, yv), (x_l, yn), (xn, yn)]
            _zp_linie_pfad(pdf, punkte, farbe)

        # Legende auf der letzten Seite
        if seiten_nr == len(seiten) - 1:
            ly = max(y_ende, kopf_y + kopf_h) + 5
            pdf.set_font("Helvetica", "", 7)
            x = _ZP_RAND
            pdf.set_line_width(0.2)

            def eintrag(text: str, zeichen) -> None:
                nonlocal x
                zeichen(x, ly)
                pdf.set_font("Helvetica", "", 7)
                _set_text(pdf)
                pdf.set_xy(x + 8, ly - 1.8)
                breite = pdf.get_string_width(text) + 1
                pdf.cell(breite, 3.6, _pdf_safe_text(text))
                x += 8 + breite + 5

            def z_balken(farbe, dunkel=None, rand=None):
                def zeichne(px: float, py: float) -> None:
                    pdf.set_fill_color(*farbe)
                    pdf.rect(px, py - 1.5, 6, 3, style="F")
                    if dunkel:
                        pdf.set_fill_color(*dunkel)
                        pdf.rect(px, py - 1.5, 3, 3, style="F")
                    if rand:
                        pdf.set_draw_color(*rand)
                        pdf.set_line_width(0.5)
                        pdf.rect(px, py - 1.5, 6, 3, style="D")

                return zeichne

            eintrag("Arbeitsschritt (dunkel = Fortschritt)", z_balken(_AKZENT, _ZP_AKZENT_DUNKEL))
            eintrag("Fremdgewerk", z_balken(_ZP_VIOLETT, _ZP_VIOLETT_DUNKEL))
            eintrag("Phase", lambda px, py: (pdf.set_fill_color(*_ZP_PHASE), pdf.rect(px, py - 0.6, 6, 1.2, style="F")))
            eintrag(
                "Meilenstein",
                lambda px, py: (
                    pdf.set_fill_color(30, 30, 30),
                    pdf.polygon([(px + 3, py - 2), (px + 5, py), (px + 3, py + 2), (px + 1, py)], style="F"),
                ),
            )
            eintrag(
                "Lieferung",
                lambda px, py: (
                    pdf.set_fill_color(30, 30, 30),
                    pdf.polygon([(px + 1.5, py - 1.6), (px + 3.1, py), (px + 1.5, py + 1.6), (px - 0.1, py)], style="F"),
                    pdf.set_fill_color(234, 120, 0),
                    pdf.rect(px + 3.7, py - 1.1, 2.2, 2.2, style="F"),
                ),
            )
            if mit_basis:
                eintrag("Basisplan", lambda px, py: (pdf.set_fill_color(*_ZP_SCHATTEN), pdf.rect(px, py - 0.7, 6, 1.5, style="F")))
            if kritischer_pfad:
                eintrag("Kritischer Pfad", z_balken(_AKZENT, None, _ZP_ROT))
            eintrag(
                "Heute",
                lambda px, py: (
                    pdf.set_draw_color(*_ZP_HEUTE),
                    pdf.set_line_width(0.4),
                    pdf.line(px + 3, py - 2.5, px + 3, py + 2.5),
                ),
            )
    return bytes(pdf.output())
