from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.vorgang import Leistungstyp, VorgangAbrechnungsart, VorgangRead

DauerauftragModus = Literal["rollierend", "fest"]


class DauerauftragZielRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    anlage_id: UUID | None
    naechste_faelligkeit_am: date
    offener_vorgang_id: UUID | None


class DauerauftragCreate(BaseModel):
    kunde_id: UUID
    # Eine oder mehrere Anlagen desselben Kunden, die dieser Dauerauftrag
    # buendeln soll -- jede bekommt ihr eigenes Ziel mit eigenem Zyklus.
    # Leer/weggelassen: ein einzelnes Ziel ohne Anlagenbezug (Kunde direkt).
    anlage_ids: list[UUID] = Field(default_factory=list)
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
    abrechnungsart: VorgangAbrechnungsart | None = None
    leistungstyp: Leistungstyp | None = None
    intervall_tage: int | None = Field(default=None, gt=0)
    modus: DauerauftragModus | None = None
    toleranz_frueh_tage: int | None = Field(default=None, ge=0)
    toleranz_spaet_tage: int | None = Field(default=None, ge=0)
    aktiv: bool | None = None


class DauerauftragZieleUpdate(BaseModel):
    """Ersetzt die komplette Anlagen-Menge eines Buendels: neue Anlagen
    bekommen ein frisches Ziel (Start = angegebenes naechste_faelligkeit_am),
    entfallene Anlagen werden samt ihres Zyklus entfernt -- ein offener
    Vorgang eines entfernten Ziels bleibt aber unangetastet bestehen, er
    verliert nur die Verknuepfung."""

    anlage_ids: list[UUID]
    naechste_faelligkeit_am: date


class DauerauftragRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kunde_id: UUID
    titel: str
    beschreibung: str | None
    abrechnungsart: VorgangAbrechnungsart
    leistungstyp: Leistungstyp
    intervall_tage: int
    modus: DauerauftragModus
    toleranz_frueh_tage: int | None
    toleranz_spaet_tage: int | None
    aktiv: bool
    created_at: datetime
    updated_at: datetime
    ziele: list[DauerauftragZielRead]
    anzahl_ziele: int
    naechste_faelligkeit_am: date | None


class DauerauftragMitVerlauf(DauerauftragRead):
    vorgaenge: list[VorgangRead]
