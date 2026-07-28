from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MandantStatus = Literal["aktiv", "pausiert", "gekuendigt"]


class MandantCreate(BaseModel):
    name: str
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", min_length=2, max_length=255)
    branche: str | None = None
    branding: dict = Field(default_factory=dict)


class MandantUpdate(BaseModel):
    name: str | None = None
    branche: str | None = None
    status: MandantStatus | None = None
    branding: dict | None = None


class MandantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    branche: str | None
    status: MandantStatus
    branding: dict
    created_at: datetime
    updated_at: datetime
