from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

PruefzyklusEinheit = Literal["tag", "woche", "monat", "stunde"]


class PruefzyklusCreate(BaseModel):
    anlage_id: UUID
    bezeichnung: str
    intervall_wert: int
    intervall_einheit: PruefzyklusEinheit = "monat"
    letzte_pruefung_am: date | None = None


class PruefzyklusUpdate(BaseModel):
    bezeichnung: str | None = None
    intervall_wert: int | None = None
    intervall_einheit: PruefzyklusEinheit | None = None
    letzte_pruefung_am: date | None = None
    naechste_pruefung_am: datetime | None = None
    aktiv: bool | None = None


class PruefzyklusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    anlage_id: UUID
    bezeichnung: str
    intervall_wert: int
    intervall_einheit: PruefzyklusEinheit
    letzte_pruefung_am: datetime | None
    naechste_pruefung_am: datetime
    aktiv: bool
    offener_vorgang_id: UUID | None
    created_at: datetime
    updated_at: datetime
