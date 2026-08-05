from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LieferantCreate(BaseModel):
    name: str
    email: str | None = None
    telefon: str | None = None
    notiz: str | None = None


class LieferantUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    telefon: str | None = None
    notiz: str | None = None


class LieferantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str | None
    telefon: str | None
    notiz: str | None
    created_at: datetime
    updated_at: datetime
