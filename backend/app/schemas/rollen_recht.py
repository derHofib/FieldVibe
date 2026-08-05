from typing import Literal

from pydantic import BaseModel

RechteRolle = Literal["controller", "mitarbeiter"]
RechteBereich = Literal[
    "vorgaenge", "kunden", "material", "dispo", "abrechnung", "statistik", "mitarbeiterverwaltung"
]
RechteAktion = Literal["sehen", "bearbeiten"]


class RechteMatrixEintrag(BaseModel):
    rolle: RechteRolle
    bereich: RechteBereich
    aktion: RechteAktion
    erlaubt: bool


class RechtSetzen(BaseModel):
    rolle: RechteRolle
    bereich: RechteBereich
    aktion: RechteAktion
    erlaubt: bool
