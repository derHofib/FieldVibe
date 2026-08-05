from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

VertragAbrechnungsart = Literal["pauschale", "aufwand", "festpreis", "wartungsvertrag"]


class VertragCreate(BaseModel):
    kunde_id: UUID
    anlage_id: UUID | None = None
    bezeichnung: str
    abrechnungsart: VertragAbrechnungsart
    konditionen: dict = {}
    laufzeit_von: date | None = None
    laufzeit_bis: date | None = None


class VertragUpdate(BaseModel):
    bezeichnung: str | None = None
    konditionen: dict | None = None
    laufzeit_von: date | None = None
    laufzeit_bis: date | None = None
    aktiv: bool | None = None


class VertragRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kunde_id: UUID
    anlage_id: UUID | None
    bezeichnung: str
    abrechnungsart: VertragAbrechnungsart
    konditionen: dict
    laufzeit_von: date | None
    laufzeit_bis: date | None
    aktiv: bool
    created_at: datetime
    updated_at: datetime
