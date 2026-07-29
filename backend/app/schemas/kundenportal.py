from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class CurrentKunde(BaseModel):
    zugang_id: UUID
    kunde_id: UUID
    kunde_name: str
    name: str
    email: str


class KundenportalZugangCreate(BaseModel):
    email: EmailStr
    password: str
    name: str


class KundenportalZugangUpdate(BaseModel):
    name: str | None = None
    aktiv: bool | None = None


class KundenAngebotAntwort(BaseModel):
    status: str


class KundenportalZugangRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kunde_id: UUID
    email: str
    name: str
    aktiv: bool
    created_at: datetime
    updated_at: datetime
