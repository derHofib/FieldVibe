from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StandortCreate(BaseModel):
    kunde_id: UUID
    bezeichnung: str
    adresse: dict = Field(default_factory=dict)
    geo_lat: float | None = None
    geo_lng: float | None = None


class StandortUpdate(BaseModel):
    bezeichnung: str | None = None
    adresse: dict | None = None
    aktiv: bool | None = None
    geo_lat: float | None = None
    geo_lng: float | None = None


class StandortRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kunde_id: UUID
    bezeichnung: str
    adresse: dict
    aktiv: bool
    geo_lat: float | None
    geo_lng: float | None
    erstellt_von_kundenportal_zugang_id: UUID | None
    created_at: datetime
    updated_at: datetime
