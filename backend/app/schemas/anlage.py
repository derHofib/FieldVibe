from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AnlageCreate(BaseModel):
    kunde_id: UUID
    bezeichnung: str
    adresse: dict
    anlagentyp: str | None = None
    qr_code: str | None = None
    stammdaten: dict = {}
    geo_lat: float | None = None
    geo_lng: float | None = None


class AnlageUpdate(BaseModel):
    bezeichnung: str | None = None
    adresse: dict | None = None
    anlagentyp: str | None = None
    qr_code: str | None = None
    stammdaten: dict | None = None
    geo_lat: float | None = None
    geo_lng: float | None = None


class AnlageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kunde_id: UUID
    bezeichnung: str
    adresse: dict
    anlagentyp: str | None
    qr_code: str | None
    stammdaten: dict
    geo_lat: float | None
    geo_lng: float | None
    created_at: datetime
    updated_at: datetime
