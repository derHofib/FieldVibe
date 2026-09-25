from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# Muss mit MANDANT_FAHRZEIT_ABRECHNUNG in app/models/mandant.py
# uebereinstimmen (docs/konzepte/ZEITERFASSUNG.md, Abschnitt 5.3/8).
FahrzeitAbrechnung = Literal["keine", "zeit", "km", "zeit_und_km"]


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
    fahrzeit_abrechnung: FahrzeitAbrechnung


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
    fahrzeit_abrechnung: FahrzeitAbrechnung | None = None


class MandantLogoUrl(BaseModel):
    url: str | None
