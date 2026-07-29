from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PruefzyklusCreate(BaseModel):
    anlage_id: UUID
    bezeichnung: str
    intervall_monate: int
    letzte_pruefung_am: date | None = None


class PruefzyklusUpdate(BaseModel):
    bezeichnung: str | None = None
    intervall_monate: int | None = None
    letzte_pruefung_am: date | None = None
    naechste_pruefung_am: date | None = None
    aktiv: bool | None = None


class PruefzyklusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    anlage_id: UUID
    bezeichnung: str
    intervall_monate: int
    letzte_pruefung_am: date | None
    naechste_pruefung_am: date
    aktiv: bool
    offener_vorgang_id: UUID | None
    created_at: datetime
    updated_at: datetime
