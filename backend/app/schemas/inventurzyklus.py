from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InventurZyklusCreate(BaseModel):
    lager_id: UUID
    intervall_tage: int = Field(gt=0)
    naechste_inventur_am: date | None = None


class InventurZyklusUpdate(BaseModel):
    intervall_tage: int | None = Field(default=None, gt=0)
    letzte_inventur_am: date | None = None
    naechste_inventur_am: date | None = None
    aktiv: bool | None = None


class InventurZyklusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lager_id: UUID
    intervall_tage: int
    letzte_inventur_am: date | None
    naechste_inventur_am: date
    aktiv: bool
    created_at: datetime
    updated_at: datetime
