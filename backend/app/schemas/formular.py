from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.formular import FORMULARFELD_TYPEN_MIT_DATENQUELLE, NUTZBARE_BREITE_MM
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

FormularfeldDatenquelle = Literal[
    "vorgang.vorgangsnummer",
    "vorgang.titel",
    "vorgang.beschreibung",
    "vorgang.leistungstyp",
    "vorgang.faelligkeit_am",
    "vorgang.adresse",
    "vorgang.zugewiesener_name",
    "kunde.kundennummer",
    "kunde.name",
    "kunde.adresse",
    "kunde.ansprechpartner",
    "anlage.bezeichnung",
    "anlage.adresse",
    "anlage.hersteller",
    "anlage.modell",
    "anlage.seriennummer",
    "anlage.anlagentyp",
    "standort.bezeichnung",
    "standort.adresse",
]


def _pruefe_datenquelle(feld_typ: str | None, datenquelle: str | None) -> None:
    if datenquelle is not None and feld_typ is not None and feld_typ not in FORMULARFELD_TYPEN_MIT_DATENQUELLE:
        raise ValueError(
            f"datenquelle ist fuer feld_typ '{feld_typ}' nicht zulaessig "
            f"(nur {', '.join(FORMULARFELD_TYPEN_MIT_DATENQUELLE)})"
        )


def _pruefe_position_bounds(x_mm: float, breite_mm: float) -> None:
    if x_mm + breite_mm > NUTZBARE_BREITE_MM:
        raise ValueError(f"x_mm + breite_mm darf {NUTZBARE_BREITE_MM} nicht ueberschreiten")


class FormularfeldCreate(BaseModel):
    feld_typ: FormularfeldTyp
    label: str
    hilfetext: str | None = None
    pflichtfeld: bool = False
    optionen: dict = {}
    seite: int = Field(default=0, ge=0)
    x_mm: float = Field(default=0, ge=0)
    y_mm: float = Field(default=0, ge=0)
    breite_mm: float = Field(default=NUTZBARE_BREITE_MM, gt=0)
    hoehe_mm: float = Field(default=8, gt=0)
    datenquelle: FormularfeldDatenquelle | None = None

    @model_validator(mode="after")
    def _validate(self) -> "FormularfeldCreate":
        _pruefe_datenquelle(self.feld_typ, self.datenquelle)
        _pruefe_position_bounds(self.x_mm, self.breite_mm)
        return self


class FormularfeldUpdate(BaseModel):
    feld_typ: FormularfeldTyp | None = None
    label: str | None = None
    hilfetext: str | None = None
    pflichtfeld: bool | None = None
    optionen: dict | None = None
    datenquelle: FormularfeldDatenquelle | None = None

    @model_validator(mode="after")
    def _validate_datenquelle(self) -> "FormularfeldUpdate":
        _pruefe_datenquelle(self.feld_typ, self.datenquelle)
        return self


class FormularfeldPosition(BaseModel):
    """Payload fuer PUT /api/formulare/{id}/felder/positionen -- ein
    Bulk-Update aller freien Positionen nach Drag&Drop/Resize im
    Canvas-Editor (ersetzt das frühere Einzel-PATCH je Feld). Ueberlappende
    Felder sind erlaubt (wie in Access) -- es wird nur geprueft, dass jedes
    Feld auf eine vorhandene Seite passt."""

    id: UUID
    seite: int = Field(ge=0)
    x_mm: float = Field(ge=0)
    y_mm: float = Field(ge=0)
    breite_mm: float = Field(gt=0)
    hoehe_mm: float = Field(gt=0)

    @model_validator(mode="after")
    def _validate(self) -> "FormularfeldPosition":
        _pruefe_position_bounds(self.x_mm, self.breite_mm)
        return self


class FormularfeldRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    feld_typ: FormularfeldTyp
    label: str
    hilfetext: str | None
    pflichtfeld: bool
    reihenfolge: int
    optionen: dict
    seite: int
    x_mm: float
    y_mm: float
    breite_mm: float
    hoehe_mm: float
    datenquelle: FormularfeldDatenquelle | None


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
    snap_mm: int | None = Field(default=None, ge=1, le=50)


class FormularUpdate(BaseModel):
    name: str | None = None
    beschreibung: str | None = None
    aktiv: bool | None = None
    snap_mm: int | None = Field(default=None, ge=1, le=50)
    # Erhoehen fuegt eine leere A4-Seite hinzu ("Seite hinzufuegen" im
    # Editor); Verringern wird in der Route abgelehnt, solange noch Felder
    # auf einer wegfallenden Seite liegen (siehe update_formular).
    anzahl_seiten: int | None = Field(default=None, ge=1)


class FormularRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    beschreibung: str | None
    aktiv: bool
    erstellt_von: UUID | None
    anzahl_seiten: int
    snap_mm: int | None
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
