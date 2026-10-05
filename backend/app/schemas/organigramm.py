from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OrgEinheitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    typ: str
    parent_id: UUID | None
    archiviert_am: datetime | None


class PositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    parent_id: UUID | None
    typ: str
    titel: str
    ebene: int | None
    org_einheit_id: UUID | None
    account_typ_id: UUID | None
    geplant: bool
    soll_besetzung: int
    gueltig_ab: date | None
    gueltig_bis: date | None
    archiviert_am: datetime | None
    reihenfolge: int


class PositionBesetzungRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position_id: UUID
    user_id: UUID
    art: str
    gueltig_von: datetime
    gueltig_bis: datetime | None


class RechtOverrideRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bereich: str
    aktion: str
    wirkung: str
    scope: str | None
