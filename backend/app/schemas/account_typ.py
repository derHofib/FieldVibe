from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

RechteBereich = Literal[
    "vorgaenge",
    "kunden",
    "material",
    "dispo",
    "abrechnung",
    "statistik",
    "mitarbeiterverwaltung",
    "formulare",
    "partner",
    "projekte",
]
RechteAktion = Literal["sehen", "erstellen", "bearbeiten", "loeschen"]


class AccountTypCreate(BaseModel):
    name: str
    icon: str | None = None
    farbe: str | None = None
    nur_zugewiesene_kunden: bool = False
    darf_vorgaenge_selbst_uebernehmen: bool = False


class AccountTypUpdate(BaseModel):
    name: str | None = None
    icon: str | None = None
    farbe: str | None = None
    nur_zugewiesene_kunden: bool | None = None
    darf_vorgaenge_selbst_uebernehmen: bool | None = None
    reihenfolge: int | None = None


class AccountTypRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    icon: str | None
    farbe: str | None
    nur_zugewiesene_kunden: bool
    darf_vorgaenge_selbst_uebernehmen: bool
    reihenfolge: int
    anzahl_nutzer: int = 0


class RechteMatrixEintrag(BaseModel):
    bereich: RechteBereich
    aktion: RechteAktion
    erlaubt: bool


class RechtSetzen(BaseModel):
    bereich: RechteBereich
    aktion: RechteAktion
    erlaubt: bool
