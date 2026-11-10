from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, model_validator

from app.core.rechte_registry import alle_aktionen, alle_bereich_keys, ist_gueltig


def _bereich_pruefen(wert: str) -> str:
    if wert not in alle_bereich_keys():
        raise ValueError("Unbekannter Bereich")
    return wert


def _aktion_pruefen(wert: str) -> str:
    if wert not in alle_aktionen():
        raise ValueError("Unbekannte Aktion")
    return wert


# Gueltigkeit kommt aus der Registry (app/core/rechte_registry.py), nicht aus
# einem Literal -- neue Bereiche/Aktionen brauchen so nur einen Registry-Eintrag.
RechteBereich = Annotated[str, AfterValidator(_bereich_pruefen)]
RechteAktion = Annotated[str, AfterValidator(_aktion_pruefen)]


class AccountTypCreate(BaseModel):
    name: str
    icon: str | None = None
    farbe: str | None = None
    nur_zugewiesene_kunden: bool = False
    darf_vorgaenge_selbst_uebernehmen: bool = False
    darf_zeiten_buchen: bool = False
    darf_abwesenheiten_verwalten: bool = False


class AccountTypUpdate(BaseModel):
    name: str | None = None
    icon: str | None = None
    farbe: str | None = None
    nur_zugewiesene_kunden: bool | None = None
    darf_vorgaenge_selbst_uebernehmen: bool | None = None
    darf_zeiten_buchen: bool | None = None
    darf_abwesenheiten_verwalten: bool | None = None
    reihenfolge: int | None = None


class AccountTypRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    icon: str | None
    farbe: str | None
    nur_zugewiesene_kunden: bool
    darf_vorgaenge_selbst_uebernehmen: bool
    darf_zeiten_buchen: bool
    darf_abwesenheiten_verwalten: bool
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

    @model_validator(mode="after")
    def _kombination_pruefen(self) -> "RechtSetzen":
        if not ist_gueltig(self.bereich, self.aktion):
            raise ValueError("Diese Aktion gibt es für diesen Bereich nicht")
        return self
