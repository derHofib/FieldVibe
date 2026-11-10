from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.projekt import ZeitplanRead

ZeitplanAntragArt = Literal["verschieben", "dauer_aendern", "problem"]
ZeitplanAntragStatus = Literal["offen", "angenommen", "abgelehnt", "zurueckgezogen"]


class ZeitplanAntragCreate(BaseModel):
    element_id: UUID
    art: ZeitplanAntragArt
    gewuenschter_start_am: date | None = None
    gewuenschtes_ende_am: date | None = None
    begruendung: str = Field(min_length=1, max_length=2000)

    @field_validator("begruendung")
    @classmethod
    def _nicht_leer(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Begründung darf nicht leer sein")
        return v


class ZeitplanAntragAnnehmen(BaseModel):
    antwort: str | None = Field(default=None, max_length=2000)


class ZeitplanAntragAblehnen(BaseModel):
    antwort: str = Field(min_length=1, max_length=2000)

    @field_validator("antwort")
    @classmethod
    def _nicht_leer(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Antwort darf nicht leer sein")
        return v


class ZeitplanAntragRead(BaseModel):
    id: UUID
    element_id: UUID
    element_titel: str
    art: ZeitplanAntragArt
    gewuenschter_start_am: date | None
    gewuenschtes_ende_am: date | None
    aktueller_start_am: date | None
    aktuelles_ende_am: date | None
    begruendung: str
    status: ZeitplanAntragStatus
    antwort: str | None
    erstellt_von: UUID
    erstellt_von_name: str | None
    erstellt_am: datetime
    bearbeitet_von_name: str | None
    bearbeitet_am: datetime | None


class ZeitplanAntragEntscheidungRead(BaseModel):
    antrag: ZeitplanAntragRead
    zeitplan: ZeitplanRead


class ZeitplanMeinRead(BaseModel):
    id: UUID
    name: str
    naechster_schritt_titel: str | None
    naechster_schritt_start: date | None
