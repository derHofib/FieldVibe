from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.mandant_einstellungen import Bundesland

# Gleiche Grenzen wie die CHECK-Constraints aus Migration 0100.
_Stunden = Field(default=Decimal("0"), ge=0, le=24, decimal_places=2)


class ArbeitszeitSollSetzen(BaseModel):
    gueltig_ab: date
    stunden_mo: Decimal = _Stunden
    stunden_di: Decimal = _Stunden
    stunden_mi: Decimal = _Stunden
    stunden_do: Decimal = _Stunden
    stunden_fr: Decimal = _Stunden
    stunden_sa: Decimal = _Stunden
    stunden_so: Decimal = _Stunden


class ArbeitszeitSollRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    gueltig_ab: date
    stunden_mo: Decimal
    stunden_di: Decimal
    stunden_mi: Decimal
    stunden_do: Decimal
    stunden_fr: Decimal
    stunden_sa: Decimal
    stunden_so: Decimal
    created_at: datetime


class FeiertagCreate(BaseModel):
    datum: date
    bezeichnung: str = Field(min_length=1, max_length=200)


class FeiertagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    datum: date
    bezeichnung: str


class FeiertageGenerieren(BaseModel):
    jahr: int = Field(ge=2000, le=2100)


class FeiertageGenerierenErgebnis(BaseModel):
    angelegt: int
    uebersprungen: int
    feiertage: list[FeiertagRead]


class BundeslandRead(BaseModel):
    bundesland: Bundesland | None


class BundeslandUpdate(BaseModel):
    bundesland: Bundesland | None


class SaldoTagRead(BaseModel):
    datum: date
    soll: Decimal
    ist: Decimal
    saldo: Decimal
    feiertag: bool
    abwesenheit: Literal["urlaub", "krankheit", "freizeitausgleich"] | None


class SaldoRead(BaseModel):
    soll_stunden: Decimal
    ist_stunden: Decimal
    saldo_stunden: Decimal
    tage: list[SaldoTagRead]
