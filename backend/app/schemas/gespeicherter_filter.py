from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

GespeicherterFilterEntitaet = Literal[
    "vorgaenge", "anlagen", "kunden", "standorte", "rechnungen"
]


class GespeicherterFilterCreate(BaseModel):
    entitaet: GespeicherterFilterEntitaet
    name: str
    filter_json: dict = Field(default_factory=dict)
    ist_standard: bool = False


class GespeicherterFilterUpdate(BaseModel):
    name: str | None = None
    filter_json: dict | None = None
    ist_standard: bool | None = None


class GespeicherterFilterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entitaet: GespeicherterFilterEntitaet
    name: str
    filter_json: dict
    ist_standard: bool
    created_at: datetime
    updated_at: datetime
