from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MaterialBewegungTyp = Literal["eingang", "umlagerung", "verwendung", "korrektur"]


class MaterialBestandRead(BaseModel):
    lager_id: UUID
    lager_bezeichnung: str
    menge: Decimal


class MaterialCreate(BaseModel):
    bezeichnung: str
    einheit: str = "Stk"
    mindestbestand: Decimal = Decimal("0")
    einzelpreis: Decimal | None = None
    lieferant_id: UUID | None = None
    artikelnummer: str | None = None
    bestell_url: str | None = None
    # Anfangsbestand landet an diesem Lagerort (Default: Zentrallager des
    # Mandanten) -- weiterer Bestand kommt ueber Wareneingang/Umlagerung dazu.
    lager_id: UUID | None = None
    menge: Decimal = Field(default=Decimal("0"), ge=0)


class MaterialUpdate(BaseModel):
    bezeichnung: str | None = None
    einheit: str | None = None
    mindestbestand: Decimal | None = None
    einzelpreis: Decimal | None = None
    lieferant_id: UUID | None = None
    artikelnummer: str | None = None
    bestell_url: str | None = None


class MaterialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bezeichnung: str
    einheit: str
    mindestbestand: Decimal
    einzelpreis: Decimal | None
    lieferant_id: UUID | None
    artikelnummer: str | None
    bestell_url: str | None
    created_at: datetime
    updated_at: datetime
    bestand_gesamt: Decimal
    bestaende: list[MaterialBestandRead]
    tag_ids: list[UUID]


class MaterialBestandSetzen(BaseModel):
    menge: Decimal = Field(ge=0)


class MaterialUmlagernRequest(BaseModel):
    von_lager_id: UUID
    nach_lager_id: UUID
    menge: Decimal = Field(gt=0)


class MaterialVerwendungCreate(BaseModel):
    vorgang_id: UUID
    lager_id: UUID
    menge: Decimal = Field(gt=0)


class MaterialVerwendungRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    material_id: UUID
    lager_id: UUID
    vorgang_id: UUID
    menge: Decimal
    verwendet_von: UUID
    created_at: datetime


class MaterialBewegungRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    material_id: UUID
    typ: MaterialBewegungTyp
    von_lager_id: UUID | None
    nach_lager_id: UUID | None
    menge: Decimal
    vorgang_id: UUID | None
    erstellt_von: UUID
    created_at: datetime
