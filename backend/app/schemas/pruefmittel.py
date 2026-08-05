from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PruefmittelCreate(BaseModel):
    bezeichnung: str
    seriennummer: str | None = None
    zugewiesen_an: UUID | None = None
    kalibrierintervall_monate: int
    letzte_kalibrierung_am: date | None = None


class PruefmittelUpdate(BaseModel):
    bezeichnung: str | None = None
    seriennummer: str | None = None
    zugewiesen_an: UUID | None = None
    kalibrierintervall_monate: int | None = None
    letzte_kalibrierung_am: date | None = None
    naechste_kalibrierung_am: date | None = None
    status: str | None = None


class PruefmittelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bezeichnung: str
    seriennummer: str | None
    zugewiesen_an: UUID | None
    kalibrierintervall_monate: int
    letzte_kalibrierung_am: date | None
    naechste_kalibrierung_am: date
    status: str
    created_at: datetime
    updated_at: datetime
