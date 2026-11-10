from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

AbwesenheitArt = Literal["urlaub", "krankheit", "freizeitausgleich"]
AbwesenheitStatus = Literal["offen", "genehmigt", "abgelehnt", "zurueckgezogen"]


class AbwesenheitCreate(BaseModel):
    art: AbwesenheitArt
    von: date
    bis: date
    halber_tag_von: bool = False
    halber_tag_bis: bool = False
    notiz: str | None = Field(default=None, max_length=2000)
    # Nur mit Recht "Abwesenheiten verwalten" fuer andere Mitarbeiter.
    user_id: UUID | None = None

    @model_validator(mode="after")
    def _zeitraum(self) -> "AbwesenheitCreate":
        if self.bis < self.von:
            raise ValueError("'bis' liegt vor 'von'")
        return self

    @field_validator("notiz")
    @classmethod
    def _notiz_trim(cls, v: str | None) -> str | None:
        return (v.strip() or None) if v is not None else None


class AbwesenheitAblehnen(BaseModel):
    antwort: str | None = Field(default=None, max_length=2000)


class AbwesenheitRead(BaseModel):
    id: UUID
    user_id: UUID
    user_name: str
    art: AbwesenheitArt
    von: date
    bis: date
    halber_tag_von: bool
    halber_tag_bis: bool
    tage: Decimal
    status: AbwesenheitStatus
    notiz: str | None
    antwort: str | None
    erstellt_von: UUID
    erstellt_am: datetime
    bearbeitet_von: UUID | None
    bearbeitet_am: datetime | None


class UrlaubsanspruchSetzen(BaseModel):
    tage: Decimal = Field(ge=0, le=999, decimal_places=1)
    resturlaub_tage: Decimal = Field(default=Decimal("0"), ge=0, le=999, decimal_places=1)
    resturlaub_verfaellt_am: date | None = None


class UrlaubsanspruchRead(BaseModel):
    user_id: UUID
    jahr: int
    tage: Decimal
    resturlaub_tage: Decimal
    resturlaub_verfaellt_am: date | None


class UrlaubskontoRead(BaseModel):
    user_id: UUID
    jahr: int
    anspruch: Decimal
    resturlaub: Decimal
    resturlaub_verfaellt_am: date | None
    # Teil des Resturlaubs, der bis zum Stichtag nicht verbraucht wurde und
    # (nach dem Stichtag) verfallen ist; vorher immer 0.
    resturlaub_verfallen: Decimal
    genommen: Decimal
    beantragt: Decimal
    verbleibend: Decimal


class KalenderEintragRead(BaseModel):
    id: UUID
    user_id: UUID
    user_name: str
    art: AbwesenheitArt
    von: date
    bis: date
    halber_tag_von: bool
    halber_tag_bis: bool
    tage: Decimal
