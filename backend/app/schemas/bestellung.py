from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

BestellungStatus = Literal["entwurf", "bestellt", "eingegangen"]


class BestellungAusBedarfenCreate(BaseModel):
    material_bedarf_ids: list[UUID]
    lieferant_id: UUID | None = None
    notiz: str | None = None


class BestellungUpdate(BaseModel):
    status: BestellungStatus | None = None
    lieferant_id: UUID | None = None
    notiz: str | None = None
    # Beim Wareneingang (status="eingegangen") koennen einzelne Positionen auf
    # den tatsaechlich bezahlten Preis korrigiert werden -- der bisherige Wert
    # war nur eine Planung zum Bestellzeitpunkt (siehe BestellungPosition).
    # Key = BestellungPosition.id.
    positionen_preise: dict[UUID, Decimal] | None = None


class BestellungPositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    material_id: UUID
    position: int
    beschreibung: str
    menge: Decimal
    einheit: str
    einzelpreis: Decimal


class BestellungRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lieferant_id: UUID | None
    bestellnummer: str
    status: BestellungStatus
    notiz: str | None
    erstellt_von: UUID
    created_at: datetime
    updated_at: datetime
    positionen: list[BestellungPositionRead]
