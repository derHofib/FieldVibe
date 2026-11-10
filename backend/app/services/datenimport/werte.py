"""Wert-Parser fuer den Datenimport: Texte bereinigen, Zahlen/Datumswerte aus
deutschen und englischen Schreibweisen lesen, Vergleichsschluessel bilden.
Alle Parser werfen ValueError mit einer Meldung, die direkt in der Zeilenmeldung
erscheinen kann (ohne den Zellwert zu wiederholen -- der steht im Bericht)."""
import re
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

# C0-Steuerzeichen (ausser Tab/LF/CR), DEL, C1 sowie unsichtbare Formatzeichen
# (Zero-Width, Bidi-Steuerung, BOM), die in Namen nichts verloren haben.
_STEUERZEICHEN = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f​-‏‪-‮⁠-⁤﻿]"
)
_LEERRAUM = re.compile(r"[ \t   ]+")
_E_MAIL = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]{2,}$")

# Erste Excel-Seriennummer, die als Datum plausibel ist (1954) bzw. nicht mehr (2119).
_EXCEL_SERIE_MIN = 20000
_EXCEL_SERIE_MAX = 80000
_EXCEL_EPOCHE = date(1899, 12, 30)


class ExcelZahl(str):
    """Zelle aus einer XLSX-Datei mit numerischem Typ. Die Zeichenkette ist nur die
    Anzeige; der exakte Wert steckt in .zahl. Ohne diese Trennung waere "1.234"
    (Float aus Excel) nicht von "1.234" (deutsch: Tausend) zu unterscheiden."""

    zahl: Decimal

    def __new__(cls, text: str, zahl: Decimal):
        obj = super().__new__(cls, text)
        obj.zahl = zahl
        return obj


def bereinige_text(wert: str | None, *, einzeilig: bool = True) -> str:
    if wert is None:
        return ""
    text = _STEUERZEICHEN.sub("", str(wert))
    if einzeilig:
        text = re.sub(r"[\r\n]+", " ", text)
        text = _LEERRAUM.sub(" ", text)
    else:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = "\n".join(_LEERRAUM.sub(" ", zeile).strip() for zeile in text.split("\n"))
        text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    # Gegenstueck zum Formelschutz im Fehlerbericht (csv_service.formel_sicher): ein Bericht,
    # der nach der Korrektur erneut hochgeladen wird, soll "'+49 ..." wieder zu "+49 ..." machen.
    if len(text) > 1 and text[0] == "'" and text[1] in "=+-@":
        text = text[1:]
    return text


def ascii_falten(text: str) -> str:
    text = text.casefold()
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(alt, neu)
    zerlegt = unicodedata.normalize("NFKD", text)
    return "".join(z for z in zerlegt if not unicodedata.combining(z))


def schluessel(text: str | None) -> str:
    """Vergleichsschluessel: Gross-/Kleinschreibung, Umlaute, Satzzeichen und
    Leerraum spielen keine Rolle ("Müller & Söhne GmbH" == "mueller soehne gmbh")."""
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "", ascii_falten(text))


def plz_schluessel(plz: str | None) -> str:
    return re.sub(r"\s+", "", plz or "")


def email_gueltig(wert: str) -> bool:
    return bool(_E_MAIL.match(wert)) and len(wert) <= 254


_UST_FORMATE = {
    "DE": re.compile(r"^DE[0-9]{9}$"),
    "AT": re.compile(r"^ATU[0-9]{8}$"),
    "ALLGEMEIN": re.compile(r"^[A-Z]{2}[A-Z0-9]{2,12}$"),
}


def ust_idnr_normalisieren(wert: str) -> tuple[str, bool]:
    """Grossschreibung ohne Leerraum/Trennzeichen; zweiter Wert: Format plausibel
    (DE: DE + 9 Ziffern, AT: ATU + 8 Ziffern, sonst Laendercode + 2-12 Zeichen).
    Nur eine Formatpruefung, keine Online-Validierung (BZSt/VIES)."""
    norm = re.sub(r"[\s.\-/]", "", wert).upper()
    land = norm[:2]
    muster = _UST_FORMATE.get(land, _UST_FORMATE["ALLGEMEIN"])
    return norm, bool(muster.match(norm))


def parse_dezimal(wert: str | None) -> Decimal | None:
    """Leer -> None. Erkennt deutsche ("1.234,56"), englische ("1,234.56") und
    schweizer ("1'234.50") Schreibweise sowie Waehrungszusaetze."""
    if wert is None:
        return None
    if isinstance(wert, ExcelZahl):
        return wert.zahl
    text = str(wert).strip()
    if not text:
        return None
    text = re.sub(r"(?i)\s*(€|eur|euro)\s*$", "", text)
    text = re.sub(r"(?i)^\s*(€|eur)\s*", "", text)
    text = re.sub(r"[\s'’]", "", text)
    if not re.fullmatch(r"[+-]?[0-9.,]+", text):
        raise ValueError("ist keine gültige Zahl")
    vorzeichen = ""
    if text[0] in "+-":
        vorzeichen, text = text[0], text[1:]
    if not text or not text[0].isdigit() and text[0] not in ".,":
        raise ValueError("ist keine gültige Zahl")
    punkt, komma = text.count("."), text.count(",")
    if punkt and komma:
        dezimal = "." if text.rfind(".") > text.rfind(",") else ","
        tausend = "," if dezimal == "." else "."
        if text.count(dezimal) > 1:
            raise ValueError("ist keine gültige Zahl")
        text = text.replace(tausend, "").replace(dezimal, ".")
    elif komma:
        # Deutsche Datei: ein einzelnes Komma ist immer das Dezimalzeichen.
        if komma > 1:
            if not re.fullmatch(r"\d{1,3}(,\d{3})+", text):
                raise ValueError("ist keine gültige Zahl")
            text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
    elif punkt:
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", text):
            text = text.replace(".", "")
        elif punkt > 1:
            raise ValueError("ist keine gültige Zahl")
    try:
        return Decimal(vorzeichen + text)
    except InvalidOperation:
        raise ValueError("ist keine gültige Zahl") from None


def parse_ganzzahl(wert: str | None) -> int | None:
    zahl = parse_dezimal(wert)
    if zahl is None:
        return None
    if zahl != zahl.to_integral_value():
        raise ValueError("muss eine ganze Zahl sein")
    return int(zahl)


_DATUM_DE = re.compile(r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2}|\d{4})$")
_DATUM_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ].*)?$")
_DATUM_KOMPAKT = re.compile(r"^(\d{4})(\d{2})(\d{2})$")


def parse_datum(wert: str | None) -> date | None:
    """TT.MM.JJJJ (auch TT.MM.JJ, TT/MM/JJJJ), JJJJ-MM-TT, JJJJMMTT und Excel-
    Seriennummern. Zweistellige Jahre: 00-69 -> 2000er, 70-99 -> 1900er."""
    if wert is None:
        return None
    if isinstance(wert, ExcelZahl):
        return _excel_serie(wert.zahl)
    text = str(wert).strip()
    if not text:
        return None
    try:
        if (treffer := _DATUM_ISO.match(text)) is not None:
            jahr, monat, tag = (int(g) for g in treffer.groups())
        elif (treffer := _DATUM_DE.match(text)) is not None:
            tag, monat, jahr = (int(g) for g in treffer.groups())
            if len(treffer.group(3)) == 2:
                jahr += 2000 if jahr < 70 else 1900
        elif (treffer := _DATUM_KOMPAKT.match(text)) is not None:
            jahr, monat, tag = (int(g) for g in treffer.groups())
        elif re.fullmatch(r"\d{5}(\.\d+)?", text):
            return _excel_serie(Decimal(text))
        else:
            raise ValueError
        ergebnis = date(jahr, monat, tag)
    except ValueError:
        raise ValueError("ist kein gültiges Datum (erwartet TT.MM.JJJJ oder JJJJ-MM-TT)") from None
    if not 1900 <= ergebnis.year <= 2200:
        raise ValueError("liegt außerhalb des zulässigen Datumsbereichs")
    return ergebnis


def _excel_serie(zahl: Decimal) -> date:
    if not _EXCEL_SERIE_MIN <= zahl <= _EXCEL_SERIE_MAX:
        raise ValueError("ist kein gültiges Datum (erwartet TT.MM.JJJJ oder JJJJ-MM-TT)")
    return _EXCEL_EPOCHE + timedelta(days=int(zahl))


def datum_als_text(wert: date | datetime) -> str:
    if isinstance(wert, datetime):
        if wert.time() == datetime.min.time():
            return wert.date().isoformat()
        return wert.replace(microsecond=0).isoformat(sep=" ")
    return wert.isoformat()


def parse_jahr(wert: str | None) -> int | None:
    """Baujahr: vierstelliges Jahr 1800 bis zum naechsten Jahr; ein volles Datum wird
    auf das Jahr gekuerzt."""
    if wert is None:
        return None
    text = str(wert).strip()
    if not text:
        return None
    if isinstance(wert, ExcelZahl):
        jahr = int(wert.zahl) if wert.zahl == wert.zahl.to_integral_value() else None
    elif re.fullmatch(r"\d{4}", text):
        jahr = int(text)
    else:
        try:
            datum = parse_datum(text)
        except ValueError:
            datum = None
        jahr = datum.year if datum else None
    if jahr is None:
        raise ValueError("ist kein gültiges Jahr")
    if not 1800 <= jahr <= date.today().year + 1:
        raise ValueError("liegt außerhalb des plausiblen Bereichs")
    return jahr


def parse_ja_nein(wert: str | None) -> bool | None:
    if wert is None or not str(wert).strip():
        return None
    text = str(wert).strip().casefold()
    if text in {"ja", "j", "yes", "y", "true", "wahr", "1", "x"}:
        return True
    if text in {"nein", "n", "no", "false", "falsch", "0"}:
        return False
    raise ValueError("muss Ja oder Nein sein")
