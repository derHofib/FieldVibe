from datetime import datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.vorgang import LEISTUNGSTYPEN

SlaKalenderArt = Literal["rund_um_die_uhr", "geschaeftszeiten"]
SlaFristArt = Literal["reaktion", "loesung"]
SlaAktion = Literal["benachrichtigen", "mail"]
SlaEmpfaenger = Literal["zugewiesener", "dispo", "vorgesetzter", "admin"]


class SlaZiel(BaseModel):
    reaktion_min: int | None = Field(default=None, gt=0, le=525_600)
    loesung_min: int | None = Field(default=None, gt=0, le=525_600)


class SlaStufe(BaseModel):
    frist_art: SlaFristArt
    schwelle_prozent: int = Field(ge=1, le=500)
    aktion: SlaAktion
    empfaenger: SlaEmpfaenger


class SlaStufeRead(SlaStufe):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position: int


def _fenster_pruefen(zeiten: dict[str, list[list[str]]]) -> dict[str, list[list[str]]]:
    for tag, fenster in zeiten.items():
        if tag not in {"0", "1", "2", "3", "4", "5", "6"}:
            raise ValueError(f"Ungültiger Wochentag: {tag}")
        letztes_ende: time | None = None
        for paar in sorted(fenster):
            if len(paar) != 2:
                raise ValueError("Ein Zeitfenster besteht aus Beginn und Ende")
            try:
                von, bis = time.fromisoformat(paar[0]), time.fromisoformat(paar[1])
            except ValueError as exc:
                raise ValueError("Zeiten im Format HH:MM angeben") from exc
            if von >= bis:
                raise ValueError("Der Beginn eines Zeitfensters muss vor dessen Ende liegen")
            if letztes_ende is not None and von < letztes_ende:
                raise ValueError("Zeitfenster eines Tages dürfen sich nicht überlappen")
            letztes_ende = bis
    return zeiten


def _ziele_pruefen(ziele):
    for prio in ziele:
        if prio not in {"1", "2", "3", "4", "5"}:
            raise ValueError(f"Ungültige Priorität: {prio}")
    return ziele


def _regeln_pruefen(regeln):
    for leistungstyp, prio in regeln.items():
        if leistungstyp not in LEISTUNGSTYPEN:
            raise ValueError(f"Unbekannter Leistungstyp: {leistungstyp}")
        if not 1 <= prio <= 5:
            raise ValueError("Priorität muss zwischen 1 und 5 liegen")
    return regeln


class _SlaRichtlinieBasis(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    beschreibung: str | None = None
    aktiv: bool = True
    ist_standard: bool = False
    kalender: SlaKalenderArt = "rund_um_die_uhr"
    geschaeftszeiten: dict[str, list[list[str]]] = {}
    feiertage_ausnehmen: bool = True
    ziele: dict[str, SlaZiel] = {}
    prioritaet_regeln: dict[str, int] = {}

    @field_validator("geschaeftszeiten")
    @classmethod
    def _zeiten(cls, wert):
        return _fenster_pruefen(wert)

    @field_validator("ziele")
    @classmethod
    def _ziele(cls, wert):
        return _ziele_pruefen(wert)

    @field_validator("prioritaet_regeln")
    @classmethod
    def _regeln(cls, wert):
        return _regeln_pruefen(wert)


class SlaRichtlinieCreate(_SlaRichtlinieBasis):
    stufen: list[SlaStufe] = []

    @model_validator(mode="after")
    def _kalender_passt(self):
        if self.kalender == "geschaeftszeiten" and not any(self.geschaeftszeiten.values()):
            raise ValueError("Für den Kalender „Geschäftszeiten“ ist mindestens ein Zeitfenster nötig")
        return self


class SlaRichtlinieUpdate(BaseModel):
    """Alle Felder optional; `stufen` ersetzt die komplette Liste."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    beschreibung: str | None = None
    aktiv: bool | None = None
    ist_standard: bool | None = None
    kalender: SlaKalenderArt | None = None
    geschaeftszeiten: dict[str, list[list[str]]] | None = None
    feiertage_ausnehmen: bool | None = None
    ziele: dict[str, SlaZiel] | None = None
    prioritaet_regeln: dict[str, int] | None = None
    stufen: list[SlaStufe] | None = None

    @field_validator("geschaeftszeiten")
    @classmethod
    def _zeiten(cls, wert):
        return None if wert is None else _fenster_pruefen(wert)

    @field_validator("ziele")
    @classmethod
    def _ziele(cls, wert):
        return None if wert is None else _ziele_pruefen(wert)

    @field_validator("prioritaet_regeln")
    @classmethod
    def _regeln(cls, wert):
        return None if wert is None else _regeln_pruefen(wert)


class SlaRichtlinieRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    beschreibung: str | None
    aktiv: bool
    ist_standard: bool
    kalender: SlaKalenderArt
    geschaeftszeiten: dict
    feiertage_ausnehmen: bool
    ziele: dict
    prioritaet_regeln: dict
    stufen: list[SlaStufeRead] = []
    created_at: datetime
    updated_at: datetime
