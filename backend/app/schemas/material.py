from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MaterialCreate(BaseModel):
    bezeichnung: str
    einheit: str = "Stk"
    bestand: Decimal = Decimal("0")
    mindestbestand: Decimal = Decimal("0")
    einzelpreis: Decimal | None = None


class MaterialUpdate(BaseModel):
    bezeichnung: str | None = None
    einheit: str | None = None
    bestand: Decimal | None = None
    mindestbestand: Decimal | None = None
    einzelpreis: Decimal | None = None


class MaterialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bezeichnung: str
    einheit: str
    bestand: Decimal
    mindestbestand: Decimal
    einzelpreis: Decimal | None
    created_at: datetime
    updated_at: datetime


class MaterialVerwendungCreate(BaseModel):
    vorgang_id: UUID
    menge: Decimal


class MaterialVerwendungRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    material_id: UUID
    vorgang_id: UUID
    menge: Decimal
    verwendet_von: UUID
    created_at: datetime
