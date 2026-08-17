from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

AngebotPositionstyp = Literal["material", "arbeitszeit"]


class AngebotPositionCreate(BaseModel):
    artikelnummer: str | None = None
    beschreibung: str
    menge: Decimal = Decimal("1")
    einheit: str = "Stk"
    einzelpreis: Decimal = Decimal("0")
    positionstyp: AngebotPositionstyp = "material"


class AngebotPositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position: int
    artikelnummer: str | None
    beschreibung: str
    menge: Decimal
    einheit: str
    einzelpreis: Decimal
    positionstyp: AngebotPositionstyp

    @computed_field  # type: ignore[prop-decorator]
    @property
    def gesamt(self) -> Decimal:
        return (self.menge * self.einzelpreis).quantize(Decimal("0.01"))


class AngebotCreate(BaseModel):
    kunde_id: UUID
    vorgang_id: UUID | None = None
    gueltig_bis: date | None = None
    positionen: list[AngebotPositionCreate] = Field(default_factory=list)


class AngebotAusMaengelnCreate(BaseModel):
    mangel_ids: list[UUID]
    gueltig_bis: date | None = None


class AngebotAusMaterialBedarfenCreate(BaseModel):
    material_bedarf_ids: list[UUID]
    gueltig_bis: date | None = None


class AngebotAusVorgangCreate(BaseModel):
    vorgang_id: UUID
    gueltig_bis: date | None = None


class AngebotUpdate(BaseModel):
    status: str | None = None
    gueltig_bis: date | None = None


class AngebotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kunde_id: UUID
    vorgang_id: UUID | None
    angebotsnummer: str
    status: str
    mwst_satz: Decimal
    gueltig_bis: date | None
    erstellt_von: UUID
    versendet_am: datetime | None
    angenommen_am: datetime | None
    abgelehnt_am: datetime | None
    created_at: datetime
    updated_at: datetime
    positionen: list[AngebotPositionRead]
    gesamt_netto: Decimal
    gesamt_brutto: Decimal
