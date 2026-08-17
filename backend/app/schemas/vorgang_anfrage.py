from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.vorgang import Leistungstyp, VorgangAbrechnungsart

VorgangAnfrageStatus = Literal["offen", "angenommen", "abgelehnt"]


class VorgangAnfrageCreate(BaseModel):
    titel: str
    beschreibung: str | None = None
    leistungstyp: Leistungstyp
    standort_id: UUID | None = None
    anlage_id: UUID | None = None


class VorgangAnfrageAnnehmen(BaseModel):
    abrechnungsart: VorgangAbrechnungsart
    prioritaet: int = Field(default=3, ge=1, le=5)


class VorgangAnfrageAblehnen(BaseModel):
    ablehnungsgrund: str | None = None


class VorgangAnfrageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kunde_id: UUID
    kundenportal_zugang_id: UUID
    standort_id: UUID | None
    anlage_id: UUID | None
    titel: str
    beschreibung: str | None
    leistungstyp: Leistungstyp
    status: VorgangAnfrageStatus
    ablehnungsgrund: str | None
    vorgang_id: UUID | None
    bearbeitet_von: UUID | None
    bearbeitet_am: datetime | None
    created_at: datetime
    updated_at: datetime
