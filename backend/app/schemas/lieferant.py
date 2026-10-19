from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.personenkonto import personenkonto_normalisieren


class LieferantCreate(BaseModel):
    name: str
    email: str | None = None
    telefon: str | None = None
    notiz: str | None = None
    kreditorenkonto: str | None = None

    @field_validator("kreditorenkonto")
    @classmethod
    def _kreditorenkonto_pruefen(cls, v: str | None) -> str | None:
        return personenkonto_normalisieren(v, "Kreditorenkonto")


class LieferantUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    telefon: str | None = None
    notiz: str | None = None
    kreditorenkonto: str | None = None

    @field_validator("kreditorenkonto")
    @classmethod
    def _kreditorenkonto_pruefen(cls, v: str | None) -> str | None:
        return personenkonto_normalisieren(v, "Kreditorenkonto")


class LieferantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str | None
    telefon: str | None
    notiz: str | None
    kreditorenkonto: str | None
    created_at: datetime
    updated_at: datetime
