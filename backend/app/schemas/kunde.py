from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

KundeTyp = Literal["privat", "gewerbe", "oeffentlich", "hausverwaltung"]


class KundeCreate(BaseModel):
    kundennummer: str | None = None
    name: str
    typ: KundeTyp | None = None
    ansprechpartner: list = Field(default_factory=list)
    adresse: dict | None = None
    notiz: str | None = None


class KundeUpdate(BaseModel):
    name: str | None = None
    typ: KundeTyp | None = None
    ansprechpartner: list | None = None
    adresse: dict | None = None
    notiz: str | None = None


class KundeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kundennummer: str
    name: str
    typ: KundeTyp | None
    ansprechpartner: list
    adresse: dict | None
    notiz: str | None
    created_at: datetime
    updated_at: datetime
