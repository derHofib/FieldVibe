from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

Role = Literal[
    "super_admin",
    "mandant_admin",
    "disponent",
    "techniker",
    "controller",
    "mitarbeiter",
    "loesch_ansicht",
    "loesch_operativ",
]


class UserCreate(BaseModel):
    mandant_id: UUID | None = None
    email: EmailStr
    password: str = Field(min_length=8)
    role: Role
    name: str

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        # E-Mail-Adressen sind ueberall case-insensitiv -- ohne diese
        # Normalisierung koennte "Dennis@Firma.de" und "dennis@firma.de" als
        # zwei verschiedene Accounts angelegt werden, und der Login (der
        # ebenfalls normalisiert, siehe app/services/auth_service.py)
        # wuerde bei abweichender Schreibweise faelschlich scheitern.
        return v.strip().lower()

    @model_validator(mode="after")
    def _mandant_required_unless_super_admin(self) -> "UserCreate":
        if self.role == "super_admin" and self.mandant_id is not None:
            raise ValueError("super_admin darf keinem Mandanten zugeordnet sein")
        if self.role != "super_admin" and self.mandant_id is None:
            raise ValueError("mandant_id ist für diese Rolle erforderlich")
        return self


class UserUpdate(BaseModel):
    name: str | None = None
    role: Role | None = None
    aktiv: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mandant_id: UUID | None
    email: str
    role: Role
    name: str
    avatar_url: str | None
    aktiv: bool
    created_at: datetime
    updated_at: datetime
