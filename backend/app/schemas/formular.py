from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.vorgang import Leistungstyp

FormularfeldTyp = Literal[
    "text",
    "textarea",
    "zahl",
    "datum",
    "dropdown",
    "mehrfachauswahl",
    "ja_nein",
    "bewertung",
    "foto",
    "unterschrift",
    "gps",
    "qr_scan",
    "abschnitt",
]
VorgangFormularStatus = Literal["offen", "abgeschlossen"]


class FormularfeldCreate(BaseModel):
    feld_typ: FormularfeldTyp
    label: str
    hilfetext: str | None = None
    pflichtfeld: bool = False
    reihenfolge: int = 0
    optionen: dict = {}


class FormularfeldUpdate(BaseModel):
    feld_typ: FormularfeldTyp | None = None
    label: str | None = None
    hilfetext: str | None = None
    pflichtfeld: bool | None = None
    reihenfolge: int | None = None
    optionen: dict | None = None


class FormularfeldRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    feld_typ: FormularfeldTyp
    label: str
    hilfetext: str | None
    pflichtfeld: bool
    reihenfolge: int
    optionen: dict


class FormularAuftragstypZuordnungCreate(BaseModel):
    leistungstyp: Leistungstyp
    pflicht_vor_abschluss: bool = False


class FormularAuftragstypZuordnungUpdate(BaseModel):
    pflicht_vor_abschluss: bool


class FormularAuftragstypZuordnungRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    leistungstyp: Leistungstyp
    pflicht_vor_abschluss: bool


class FormularCreate(BaseModel):
    name: str
    beschreibung: str | None = None


class FormularUpdate(BaseModel):
    name: str | None = None
    beschreibung: str | None = None
    aktiv: bool | None = None


class FormularRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    beschreibung: str | None
    aktiv: bool
    erstellt_von: UUID | None
    created_at: datetime
    updated_at: datetime
    felder: list[FormularfeldRead] = []
    zuordnungen: list[FormularAuftragstypZuordnungRead] = []


class FormularVerfuegbar(BaseModel):
    """Ein fuer den Leistungstyp des jeweiligen Vorgangs zugeordnetes,
    aktives Formular -- Grundlage fuer die Auswahl "Formular ausfüllen" auf
    der Vorgangsseite (siehe GET /api/vorgaenge/{id}/formulare/verfuegbar)."""

    id: UUID
    name: str
    beschreibung: str | None
    pflicht_vor_abschluss: bool


class VorgangFormularStart(BaseModel):
    formular_id: UUID


class VorgangFormularUpdate(BaseModel):
    antworten: dict


class VorgangFormularRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vorgang_id: UUID
    formular_id: UUID
    formular_snapshot: dict
    antworten: dict
    status: VorgangFormularStatus
    ausgefuellt_von: UUID | None
    kundensichtbar: bool
    abgeschlossen_am: datetime | None
    created_at: datetime
    updated_at: datetime
