import re
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
FIRMENDATEN_URL_KEYS = ("impressum_url", "datenschutz_url")

# Schluessel "<Steuerkategorie>:<Satz>" der Erloeskonto-Zuordnung in
# firmendaten["buchhaltung"]["erloeskonten"] (DATEV-Export, siehe
# auswertung_service._erloeskonto).
ERLOESKONTO_SCHLUESSEL = ("S:19.00", "S:7.00", "Z:0.00", "E:0.00", "AE:0.00")
_KONTO_MUSTER = re.compile(r"\d{4,8}")
_BU_MUSTER = re.compile(r"\d{1,3}")


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
    def _buchhaltung_pruefen(cls, v: dict | None) -> dict | None:
        if v is None or v.get("buchhaltung") is None:
            return v
        buchhaltung = v["buchhaltung"]
        if not isinstance(buchhaltung, dict):
            raise ValueError("buchhaltung muss ein Objekt sein")
        erloeskonten = buchhaltung.get("erloeskonten")
        if erloeskonten is None:
            return v
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
        return {**v, "buchhaltung": {**buchhaltung, "erloeskonten": geprueft}}


class MandantLogoUrl(BaseModel):
    url: str | None
