from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

AnlagenFeldTyp = Literal["text", "zahl", "datum"]


class AnlagenFeldDefinitionCreate(BaseModel):
    anlagentyp: str
    feld_name: str
    feld_typ: AnlagenFeldTyp = "text"
    reihenfolge: int = 0


class AnlagenFeldDefinitionUpdate(BaseModel):
    feld_name: str | None = None
    feld_typ: AnlagenFeldTyp | None = None
    reihenfolge: int | None = None


class AnlagenFeldDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    anlagentyp: str
    feld_name: str
    feld_typ: AnlagenFeldTyp
    reihenfolge: int
    created_at: datetime
    updated_at: datetime
