from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MaterialBedarfZweck = Literal["bestellung", "angebot"]
MaterialBedarfStatus = Literal["offen", "bestellt", "in_angebot", "erhalten", "storniert"]


class MaterialBedarfCreate(BaseModel):
    material_id: UUID
    vorgang_id: UUID
    menge: Decimal = Field(gt=0)
    notiz: str | None = None
    zweck: MaterialBedarfZweck = "bestellung"


class MaterialBedarfRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    material_id: UUID
    vorgang_id: UUID
    menge: Decimal
    notiz: str | None
    zweck: MaterialBedarfZweck
    status: MaterialBedarfStatus
    bestellung_id: UUID | None
    angebot_id: UUID | None
    erstellt_von: UUID
    created_at: datetime


class MaterialBedarfMitDetails(MaterialBedarfRead):
    material_bezeichnung: str
    material_einheit: str
    vorgang_titel: str
    vorgang_vorgangsnummer: str
    kunde_name: str
