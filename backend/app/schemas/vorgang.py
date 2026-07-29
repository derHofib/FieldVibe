from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

VorgangAbrechnungsart = Literal[
    "pauschale", "aufwand", "festpreis", "wartungsvertrag", "gewaehrleistung"
]
Leistungstyp = Literal["installation", "pruefung", "wartung", "stoerung", "beratung", "planung"]
VorgangStatus = Literal[
    "neu", "geplant", "in_arbeit", "wartet_kunde", "abgeschlossen", "abgerechnet", "storniert"
]


class VorgangCreate(BaseModel):
    vorgangsnummer: str | None = None
    kunde_id: UUID
    anlage_id: UUID | None = None
    vertrag_id: UUID | None = None
    parent_vorgang_id: UUID | None = None
    titel: str
    beschreibung: str | None = None
    abrechnungsart: VorgangAbrechnungsart
    leistungstyp: Leistungstyp
    prioritaet: int = Field(default=3, ge=1, le=5)
    # Von der Offline-Outbox vergeben (Nacharbeit): macht einen Sync-Retry
    # sicher idempotent, dasselbe Muster wie VorgangEventCreate.client_uuid.
    client_uuid: UUID | None = None


class VorgangUpdate(BaseModel):
    titel: str | None = None
    beschreibung: str | None = None
    anlage_id: UUID | None = None
    vertrag_id: UUID | None = None
    abrechnungsart: VorgangAbrechnungsart | None = None
    leistungstyp: Leistungstyp | None = None
    status: VorgangStatus | None = None
    prioritaet: int | None = Field(default=None, ge=1, le=5)


class VorgangRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vorgangsnummer: str
    kunde_id: UUID
    anlage_id: UUID | None
    vertrag_id: UUID | None
    parent_vorgang_id: UUID | None
    titel: str
    beschreibung: str | None
    abrechnungsart: VorgangAbrechnungsart
    leistungstyp: Leistungstyp
    status: VorgangStatus
    prioritaet: int
    last_activity_at: datetime
    abgeschlossen_am: datetime | None
    created_at: datetime
    updated_at: datetime
