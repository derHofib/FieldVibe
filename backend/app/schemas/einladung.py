from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

EinladungArt = Literal["mitarbeiter", "kunde", "partner"]
EinladungRolle = Literal["mandant_admin", "disponent", "techniker"]
EinladungStatus = Literal["offen", "angenommen", "widerrufen"]


class MitarbeiterEinladungCreate(BaseModel):
    email: EmailStr
    role: EinladungRolle
    # Nur fuer super_admin relevant (mandant_admin laedt immer in den
    # eigenen Mandanten ein, siehe app/api/routes/users.py).
    mandant_id: UUID | None = None

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class KundeEinladungCreate(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class PartnerEinladungCreate(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class EinladungRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    art: EinladungArt
    rolle: EinladungRolle | None
    kunde_id: UUID | None
    partner_id: UUID | None
    status: EinladungStatus
    abgelaufen: bool
    created_at: datetime
    angenommen_am: datetime | None
    # Nur gesetzt, wenn kein SMTP konfiguriert ist -- der einladende
    # Mitarbeiter muss den Link dann manuell weitergeben (siehe
    # app/services/einladung_service.py).
    registrierungslink: str | None = None
