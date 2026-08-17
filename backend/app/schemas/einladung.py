from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator

EinladungArt = Literal["mitarbeiter", "kunde", "partner"]
EinladungRolle = Literal["mandant_admin", "custom"]
EinladungStatus = Literal["offen", "angenommen", "widerrufen"]


class MitarbeiterEinladungCreate(BaseModel):
    email: EmailStr
    role: EinladungRolle
    # Nur bei role == "custom" gesetzt -- zeigt auf den vom mandant_admin
    # definierten Account-Typ (siehe app/models/account_typ.py), analog zu
    # UserCreate.account_typ_id.
    account_typ_id: UUID | None = None
    # Nur fuer super_admin relevant (mandant_admin laedt immer in den
    # eigenen Mandanten ein, siehe app/api/routes/users.py).
    mandant_id: UUID | None = None

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @model_validator(mode="after")
    def _account_typ_id_nur_bei_custom(self) -> "MitarbeiterEinladungCreate":
        if self.role == "custom" and self.account_typ_id is None:
            raise ValueError("account_typ_id ist für role='custom' erforderlich")
        if self.role != "custom" and self.account_typ_id is not None:
            raise ValueError("account_typ_id ist nur für role='custom' erlaubt")
        return self


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
    account_typ_id: UUID | None
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
