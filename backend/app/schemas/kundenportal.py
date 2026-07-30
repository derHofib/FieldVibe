from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


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

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class KundenportalZugangUpdate(BaseModel):
    name: str | None = None
    aktiv: bool | None = None
    # Fallback ohne konfiguriertes SMTP (siehe app/services/email_service.py):
    # ein Mitarbeiter kann das Passwort direkt neu setzen, statt den Zugang
    # deaktivieren und neu anlegen zu muessen.
    password: str | None = None


class KundenAngebotAntwort(BaseModel):
    status: str


class KundenPasswortVergessenRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class KundenPasswortResetRequest(BaseModel):
    token: str
    new_password: str


class KundenportalZugangRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kunde_id: UUID
    email: str
    name: str
    aktiv: bool
    created_at: datetime
    updated_at: datetime
