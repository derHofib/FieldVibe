from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class FristRead(BaseModel):
    belegart: str
    label: str
    jahre: int
    rechtsgrundlage: str


class LoeschvorschlagRead(BaseModel):
    entity_typ: str
    id: UUID
    beleg_nummer: str | None
    belegart: str
    fristende: date
    im_papierkorb: bool


class LoeschvorschlagListe(BaseModel):
    eintraege: list[LoeschvorschlagRead]
    gesamt: int
    stichtag: date


class S3LoeschauftragRead(BaseModel):
    id: UUID
    prefix: str
    anlass: str
    status: str
    versuche: int
    letzter_fehler: str | None
    erstellt_am: datetime
    naechster_versuch_am: datetime
