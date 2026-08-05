from pydantic import BaseModel, Field


class MandantEinstellungenRead(BaseModel):
    scheduler_stunde_utc: int | None
    effektive_scheduler_stunde_utc: int
    firmendaten: dict
    logo_object_key: str | None


class MandantEinstellungenUpdate(BaseModel):
    # None setzt explizit auf den globalen Default zurueck -- einziges Feld
    # dieser Ressource, daher kein exclude_unset-Partial-Update noetig.
    scheduler_stunde_utc: int | None = Field(default=None, ge=0, le=23)
    # Optional: nur gesetzt, wenn die Firmenstammdaten mitgeaendert werden
    # sollen -- None laesst den bestehenden Wert unveraendert (anders als
    # scheduler_stunde_utc oben gibt es hier keinen sinnvollen "auf Default
    # zuruecksetzen"-Fall, ein leeres Firmenprofil waere nie gewollt).
    firmendaten: dict | None = None


class MandantLogoUrl(BaseModel):
    url: str | None
