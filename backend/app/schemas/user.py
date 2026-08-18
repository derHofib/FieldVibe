from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

Role = Literal[
    "super_admin",
    "mandant_admin",
    "custom",
    "loesch_ansicht",
    "loesch_operativ",
]


class UserCreate(BaseModel):
    mandant_id: UUID | None = None
    email: EmailStr
    password: str = Field(min_length=8)
    role: Role
    # Nur bei role == "custom" gesetzt -- zeigt auf den vom mandant_admin
    # definierten Account-Typ (siehe app/models/account_typ.py).
    account_typ_id: UUID | None = None
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
        if self.role == "custom" and self.account_typ_id is None:
            raise ValueError("account_typ_id ist für role='custom' erforderlich")
        return self


class UserUpdate(BaseModel):
    name: str | None = None
    role: Role | None = None
    account_typ_id: UUID | None = None
    aktiv: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class BottomNavUpdate(BaseModel):
    # Feste, nicht wischbare Zone links vom Neu-Button (siehe frontend/src/
    # config/navSeiten.ts) -- genau 2 Seiten-Keys. Wischbare "Rotunde" rechts
    # vom Neu-Button -- beliebig viele Seiten-Keys. Beide None = zur
    # Standardauswahl zuruecksetzen; dies ist immer eine vollstaendige
    # Ersetzung beider Listen, kein Teil-Update.
    links: list[str] | None = None
    rotunde: list[str] | None = None


class OfficeNavUpdate(BaseModel):
    # Liste der Seiten-Keys aus frontend/src/config/navSeiten.ts, die in der
    # Office-Seitenleiste angezeigt werden sollen. None = zur Standardauswahl
    # (alle sichtbaren Seiten) zuruecksetzen -- immer vollstaendiger Ersatz,
    # kein Teil-Update.
    items: list[str] | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mandant_id: UUID | None
    email: str
    role: Role
    account_typ_id: UUID | None = None
    # Name des Account-Typs (None fuer role != "custom") -- dem Frontend
    # erspart das eine Zusatzabfrage gegen /api/account-typen nur fuer die
    # Anzeige in Listen/Dropdowns.
    account_typ_name: str | None = None
    # Gespiegelt aus AccountTyp.nur_zugewiesene_kunden (False fuer
    # role != "custom") -- ersetzt das fruehere role == "techniker" beim
    # Filtern von Zuweisungs-Dropdowns (Termine/Fahrzeuge/Kunde-Zuweisungen)
    # im Frontend.
    nur_zugewiesene_kunden: bool = False
    name: str
    avatar_url: str | None
    aktiv: bool
    created_at: datetime
    updated_at: datetime
