import re
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.public_rechtliches import ist_http_url

# Muss mit MANDANT_FAHRZEIT_ABRECHNUNG in app/models/mandant.py
# uebereinstimmen (docs/konzepte/ZEITERFASSUNG.md, Abschnitt 5.3/8).
FahrzeitAbrechnung = Literal["keine", "zeit", "km", "zeit_und_km"]

# Muss mit MANDANT_BUNDESLAENDER in app/models/mandant.py uebereinstimmen.
Bundesland = Literal[
    "BW", "BY", "BE", "BB", "HB", "HH", "HE", "MV", "NI", "NW", "RP", "SL", "SN", "ST", "SH", "TH"
]


# Optionale Rechtstext-URLs in Mandant.firmendaten; haben auf den Login-/
# Portalseiten Vorrang vor den Platzhalter-Seiten (siehe public_rechtliches).
FIRMENDATEN_URL_KEYS = ("impressum_url", "datenschutz_url", "barrierefreiheit_url")

# Muss mit e_invoice_service.E_RECHNUNG_MODI uebereinstimmen (hier nicht importiert,
# damit das Schema nicht die XML-Bibliothek nachzieht).
E_RECHNUNG_MODI = ("aus", "b2b", "alle")

# Kundenportal-Verbraucherschutz (firmendaten.portal_verbraucherschutz usw.);
# Bedeutung der Werte siehe app/services/verbraucherschutz_service.py.
PORTAL_VERBRAUCHERSCHUTZ_MODI = ("aus", "nur_privatkunden")
WIDERRUFSBELEHRUNG_TEXT_MAX = 20000
_EMAIL_MUSTER = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

# Schluessel "<Steuerkategorie>:<Satz>" der Erloeskonto-Zuordnung in
# firmendaten["buchhaltung"]["erloeskonten"] (DATEV-Export, siehe
# auswertung_service._erloeskonto).
ERLOESKONTO_SCHLUESSEL = ("S:19.00", "S:7.00", "Z:0.00", "E:0.00", "AE:0.00")
_KONTO_MUSTER = re.compile(r"\d{4,8}")
_BU_MUSTER = re.compile(r"\d{1,3}")

# DATEV-Stammdaten in firmendaten["buchhaltung"] (Header des Buchungsstapels,
# siehe datev_service); Wertebereiche laut DATEV-Vorgabe (Berater 1001-9999999,
# Mandant 1-99999).
DATEV_ZAHLENFELDER = {
    "berater_nr": (1001, 9999999),
    "mandant_nr": (1, 99999),
    "wirtschaftsjahr_beginn_monat": (1, 12),
    "sachkontenlaenge": (4, 8),
}
DATEV_KONTENRAHMEN = ("SKR03", "SKR04")


def _ganzzahl(wert: object, name: str, minimum: int, maximum: int) -> int | None:
    """Leer/None = nicht gesetzt. Strings aus Formularen sind erlaubt, Bool und
    Dezimalzahlen nicht (True waere sonst still die Beraternummer 1)."""
    if wert is None or (isinstance(wert, str) and not wert.strip()):
        return None
    if isinstance(wert, bool) or not isinstance(wert, (int, str)):
        raise ValueError(f"{name} muss eine ganze Zahl sein")
    text = str(wert).strip()
    if not text.isascii() or not text.isdigit():
        raise ValueError(f"{name} muss eine ganze Zahl sein")
    zahl = int(text)
    if not minimum <= zahl <= maximum:
        raise ValueError(f"{name} muss zwischen {minimum} und {maximum} liegen")
    return zahl


def _datev_stammdaten_pruefen(buchhaltung: dict) -> dict:
    """Normalisiert die DATEV-Stammdaten (Zahlen als int). Nicht gesetzte Felder
    entfallen, damit der Export fehlende Berater-/Mandantennummer erkennt, statt
    eine leere Zeichenkette zu verarbeiten."""
    ergebnis = {k: v for k, v in buchhaltung.items() if k not in DATEV_ZAHLENFELDER and k != "kontenrahmen"}
    for name, (minimum, maximum) in DATEV_ZAHLENFELDER.items():
        zahl = _ganzzahl(buchhaltung.get(name), name, minimum, maximum)
        if zahl is not None:
            ergebnis[name] = zahl
    kontenrahmen = buchhaltung.get("kontenrahmen")
    if kontenrahmen not in (None, ""):
        if kontenrahmen not in DATEV_KONTENRAHMEN:
            raise ValueError(f"kontenrahmen muss {' oder '.join(DATEV_KONTENRAHMEN)} sein")
        ergebnis["kontenrahmen"] = kontenrahmen
    return ergebnis


class MandantEinstellungenRead(BaseModel):
    scheduler_stunde_utc: int | None
    effektive_scheduler_stunde_utc: int
    wiedervorlage_standard_tage: int | None
    effektive_wiedervorlage_standard_tage: int
    firmendaten: dict
    logo_object_key: str | None
    # Vorbelegung fuer NEU angelegte Leistungsverzeichnis-Positionen im
    # Modus "berechnet" -- siehe app/models/leistungsverzeichnis.py. Anders
    # als scheduler_stunde_utc/wiedervorlage_standard_tage kein "NULL =
    # globaler Default"-Fallback, der Mandant traegt hier direkt den
    # tatsaechlich verwendeten Wert (Default 0).
    standard_lohn_gemeinkosten_prozent: Decimal
    standard_gewinn_wagnis_prozent: Decimal
    # Fahrzeit-Abrechnung (Stufe 4) -- km_satz_netto=NULL heisst "aus", auch
    # wenn fahrzeit_abrechnung km/zeit_und_km verlangt (siehe rechnung_service).
    km_satz_netto: Decimal | None
    # Stundensatz fuer Fahrzeit-Vorschlaege; None = Preis 0.
    fahrzeit_satz_netto: Decimal | None
    fahrzeit_abrechnung: FahrzeitAbrechnung
    bundesland: Bundesland | None = None


class MandantEinstellungenUpdate(BaseModel):
    # None setzt explizit auf den globalen Default zurueck -- kein
    # exclude_unset-Partial-Update noetig, da das Feld unabhaengig von
    # firmendaten ist (siehe unten).
    scheduler_stunde_utc: int | None = Field(default=None, ge=0, le=23)
    wiedervorlage_standard_tage: int | None = Field(default=None, gt=0)
    # Optional: nur gesetzt, wenn die Firmenstammdaten mitgeaendert werden
    # sollen -- None laesst den bestehenden Wert unveraendert (anders als
    # scheduler_stunde_utc oben gibt es hier keinen sinnvollen "auf Default
    # zuruecksetzen"-Fall, ein leeres Firmenprofil waere nie gewollt).
    firmendaten: dict | None = None
    standard_lohn_gemeinkosten_prozent: Decimal | None = Field(default=None, ge=0)
    standard_gewinn_wagnis_prozent: Decimal | None = Field(default=None, ge=0)
    # None setzt explizit zurueck auf "aus" (wie scheduler_stunde_utc oben).
    km_satz_netto: Decimal | None = Field(default=None, ge=0)
    fahrzeit_satz_netto: Decimal | None = Field(default=None, ge=0)
    fahrzeit_abrechnung: FahrzeitAbrechnung | None = None
    # None setzt zurueck (nur bundesweite Feiertage).
    bundesland: Bundesland | None = None


    @field_validator("firmendaten")
    @classmethod
    def _rechtstext_urls_pruefen(cls, v: dict | None) -> dict | None:
        if v is None:
            return v
        ergebnis = dict(v)
        for key in FIRMENDATEN_URL_KEYS:
            if key not in ergebnis or ergebnis[key] is None:
                continue
            wert = ergebnis[key]
            # Leer = "Platzhalter-Seite nutzen"; sonst nur http(s), weil der
            # Wert ungeprueft als href auf oeffentlichen Seiten landet.
            if not isinstance(wert, str) or (wert.strip() and not ist_http_url(wert.strip())):
                raise ValueError(f"{key} muss eine http(s)-URL sein oder leer bleiben")
            ergebnis[key] = wert.strip()
        return ergebnis

    @field_validator("firmendaten")
    @classmethod
    def _e_rechnung_pruefen(cls, v: dict | None) -> dict | None:
        if v is None:
            return v
        ergebnis = dict(v)
        modus = ergebnis.get("e_rechnung_modus")
        if modus is not None:
            if modus not in E_RECHNUNG_MODI:
                raise ValueError(f"e_rechnung_modus muss einer von {', '.join(E_RECHNUNG_MODI)} sein")
            # e_rechnung_aktiv bleibt als abgeleiteter Wert fuer aeltere Leser erhalten.
            ergebnis["e_rechnung_aktiv"] = modus != "aus"
        elif "e_rechnung_aktiv" in ergebnis:
            ergebnis["e_rechnung_modus"] = "alle" if ergebnis["e_rechnung_aktiv"] else "aus"
        if "privatkunden_hinweise" in ergebnis and not isinstance(ergebnis["privatkunden_hinweise"], bool):
            raise ValueError("privatkunden_hinweise muss true oder false sein")
        return ergebnis

    @field_validator("firmendaten")
    @classmethod
    def _mfa_pflicht_pruefen(cls, v: dict | None) -> dict | None:
        if v is not None and "mfa_pflicht" in v and not isinstance(v["mfa_pflicht"], bool):
            raise ValueError("mfa_pflicht muss true oder false sein")
        return v

    @field_validator("firmendaten")
    @classmethod
    def _portal_verbraucherschutz_pruefen(cls, v: dict | None) -> dict | None:
        if v is None:
            return v
        ergebnis = dict(v)
        modus = ergebnis.get("portal_verbraucherschutz")
        if modus is not None and modus not in PORTAL_VERBRAUCHERSCHUTZ_MODI:
            raise ValueError(f"portal_verbraucherschutz muss einer von {PORTAL_VERBRAUCHERSCHUTZ_MODI} sein")
        for key, grenze in (
            ("widerrufsbelehrung_text", WIDERRUFSBELEHRUNG_TEXT_MAX),
            ("widerrufsbelehrung_version", 60),
            ("barrierefreiheit_kontakt_email", 254),
            ("barrierefreiheit_stand", 10),
        ):
            wert = ergebnis.get(key)
            if wert is None:
                continue
            if not isinstance(wert, str) or len(wert.strip()) > grenze:
                raise ValueError(f"{key} muss ein Text mit höchstens {grenze} Zeichen sein")
            ergebnis[key] = wert.strip()
        kontakt = ergebnis.get("barrierefreiheit_kontakt_email")
        if kontakt and not _EMAIL_MUSTER.fullmatch(kontakt):
            raise ValueError("barrierefreiheit_kontakt_email muss eine E-Mail-Adresse sein")
        stand = ergebnis.get("barrierefreiheit_stand")
        if stand:
            try:
                date.fromisoformat(stand)
            except ValueError as exc:
                raise ValueError("barrierefreiheit_stand muss ein Datum (JJJJ-MM-TT) sein") from exc
        return ergebnis

    @field_validator("firmendaten")
    @classmethod
    def _buchhaltung_pruefen(cls, v: dict | None) -> dict | None:
        if v is None or v.get("buchhaltung") is None:
            return v
        buchhaltung = v["buchhaltung"]
        if not isinstance(buchhaltung, dict):
            raise ValueError("buchhaltung muss ein Objekt sein")
        ergebnis = _datev_stammdaten_pruefen(buchhaltung)
        erloeskonten = buchhaltung.get("erloeskonten")
        if erloeskonten is None:
            return {**v, "buchhaltung": ergebnis}
        if not isinstance(erloeskonten, dict):
            raise ValueError("buchhaltung.erloeskonten muss ein Objekt sein")
        geprueft = {}
        for schluessel, eintrag in erloeskonten.items():
            if schluessel not in ERLOESKONTO_SCHLUESSEL:
                raise ValueError(
                    f"Unbekannter Erlöskonto-Schlüssel {schluessel} (erlaubt: {', '.join(ERLOESKONTO_SCHLUESSEL)})"
                )
            if not isinstance(eintrag, dict) or set(eintrag) - {"konto", "bu"}:
                raise ValueError(f"Erlöskonto {schluessel}: erlaubt sind nur konto und bu")
            konto = str(eintrag.get("konto") or "").strip()
            if not _KONTO_MUSTER.fullmatch(konto):
                raise ValueError(f"Erlöskonto {schluessel}: konto muss 4 bis 8 Ziffern haben")
            bu = str(eintrag.get("bu") or "").strip()
            if bu and not _BU_MUSTER.fullmatch(bu):
                raise ValueError(f"Erlöskonto {schluessel}: bu muss leer sein oder 1 bis 3 Ziffern haben")
            geprueft[schluessel] = {"konto": konto, "bu": bu}
        return {**v, "buchhaltung": {**ergebnis, "erloeskonten": geprueft}}


class MandantLogoUrl(BaseModel):
    url: str | None
