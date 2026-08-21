from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.kontakt import AnsprechpartnerEintrag

KundeTyp = Literal["privat", "gewerbe", "oeffentlich", "hausverwaltung"]


class KundeCreate(BaseModel):
    kundennummer: str | None = None
    name: str
    typ: KundeTyp | None = None
    ansprechpartner: list[AnsprechpartnerEintrag] = Field(default_factory=list)
    adresse: dict | None = None
    notiz: str | None = None
    ust_idnr: str | None = None


class KundeLogoUrl(BaseModel):
    url: str | None


class KundeUpdate(BaseModel):
    name: str | None = None
    typ: KundeTyp | None = None
    ansprechpartner: list[AnsprechpartnerEintrag] | None = None
    adresse: dict | None = None
    notiz: str | None = None
    ust_idnr: str | None = None


class KundeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kundennummer: str
    name: str
    typ: KundeTyp | None
    ansprechpartner: list[AnsprechpartnerEintrag]
    adresse: dict | None
    notiz: str | None
    ust_idnr: str | None
    portal_slug: str
    logo_object_key: str | None
    created_at: datetime
    updated_at: datetime
