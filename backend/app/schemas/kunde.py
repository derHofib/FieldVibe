from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

KundeTyp = Literal["privat", "gewerbe", "oeffentlich", "hausverwaltung"]


class AnsprechpartnerEintrag(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    position: str | None = None
    telefon: str | None = None
    email: str | None = None
    # Tagesgeschaeft (Terminabsprachen etc.) vs. reiner Eskalationskontakt --
    # ein Ansprechpartner kann beides, eines von beiden oder keines sein.
    operativ: bool = False
    # 1 = Erstkontakt, 2 = Eskalation, 3 = Geschaeftsleitung/Notfall; None =
    # nicht Teil der Eskalationskette.
    eskalationsstufe: int | None = Field(default=None, ge=1, le=3)
    notiz: str | None = None


class KundeCreate(BaseModel):
    kundennummer: str | None = None
    name: str
    typ: KundeTyp | None = None
    ansprechpartner: list[AnsprechpartnerEintrag] = Field(default_factory=list)
    adresse: dict | None = None
    notiz: str | None = None


class KundeLogoUrl(BaseModel):
    url: str | None


class KundeUpdate(BaseModel):
    name: str | None = None
    typ: KundeTyp | None = None
    ansprechpartner: list[AnsprechpartnerEintrag] | None = None
    adresse: dict | None = None
    notiz: str | None = None


class KundeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kundennummer: str
    name: str
    typ: KundeTyp | None
    ansprechpartner: list[AnsprechpartnerEintrag]
    adresse: dict | None
    notiz: str | None
    portal_slug: str
    logo_object_key: str | None
    created_at: datetime
    updated_at: datetime
