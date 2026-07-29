from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.vorgang import Leistungstyp, VorgangAbrechnungsart, VorgangRead

DauerauftragModus = Literal["rollierend", "fest"]


class DauerauftragCreate(BaseModel):
    kunde_id: UUID
    anlage_id: UUID | None = None
    titel: str
    beschreibung: str | None = None
    abrechnungsart: VorgangAbrechnungsart
    leistungstyp: Leistungstyp
    intervall_tage: int = Field(gt=0)
    naechste_faelligkeit_am: date
    modus: DauerauftragModus = "rollierend"
    toleranz_frueh_tage: int | None = Field(default=None, ge=0)
    toleranz_spaet_tage: int | None = Field(default=None, ge=0)


class DauerauftragUpdate(BaseModel):
    titel: str | None = None
    beschreibung: str | None = None
    anlage_id: UUID | None = None
    abrechnungsart: VorgangAbrechnungsart | None = None
    leistungstyp: Leistungstyp | None = None
    intervall_tage: int | None = Field(default=None, gt=0)
    naechste_faelligkeit_am: date | None = None
    modus: DauerauftragModus | None = None
    toleranz_frueh_tage: int | None = Field(default=None, ge=0)
    toleranz_spaet_tage: int | None = Field(default=None, ge=0)
    aktiv: bool | None = None


class DauerauftragRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kunde_id: UUID
    anlage_id: UUID | None
    titel: str
    beschreibung: str | None
    abrechnungsart: VorgangAbrechnungsart
    leistungstyp: Leistungstyp
    intervall_tage: int
    naechste_faelligkeit_am: date
    modus: DauerauftragModus
    toleranz_frueh_tage: int | None
    toleranz_spaet_tage: int | None
    aktiv: bool
    offener_vorgang_id: UUID | None
    created_at: datetime
    updated_at: datetime


class DauerauftragMitVerlauf(DauerauftragRead):
    vorgaenge: list[VorgangRead]
