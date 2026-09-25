from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

AuftragStatus = Literal["offen", "in_arbeit", "abgeschlossen", "storniert"]


class AuftragCreate(BaseModel):
    projekt_id: UUID | None = None
    kunde_id: UUID | None = None
    titel: str
    beschreibung: str | None = None

    @field_validator("titel")
    @classmethod
    def _titel_nicht_leer(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Titel darf nicht leer sein")
        return v


class AuftragUpdate(BaseModel):
    projekt_id: UUID | None = None
    kunde_id: UUID | None = None
    titel: str | None = None
    beschreibung: str | None = None
    status: AuftragStatus | None = None

    @field_validator("titel")
    @classmethod
    def _titel_nicht_leer(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Titel darf nicht leer sein")
        return v


class AuftragRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    projekt_id: UUID | None
    kunde_id: UUID | None
    titel: str
    beschreibung: str | None
    status: AuftragStatus
    erstellt_von: UUID
    created_at: datetime
    updated_at: datetime
    # Nicht persistiert, sondern in den Routen transient gesetzt (gleiches
    # Muster wie VorgangRead.zugewiesener_name) -- erspart dem Frontend
    # zusaetzliche Kunde/Vorgang-Anzahl-Abfragen fuer die Tabellen-Ansicht.
    kunde_name: str | None = None
    vorgaenge_gesamt: int = 0
