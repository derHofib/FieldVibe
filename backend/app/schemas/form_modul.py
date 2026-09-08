from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.vorgang import Leistungstyp

FormSchemaStatus = Literal["draft", "published", "archived"]
FormViewTyp = Literal["capture", "print", "summary", "table", "public"]
FormPraesentationsTyp = Literal["heading", "richtext", "divider", "spacer", "callout", "image", "computed_text"]
FormLogicEffekt = Literal["show", "hide", "require", "readonly", "set_value"]
FormSubmissionStatus = Literal["offen", "abgeschlossen"]
FormFeldTyp = Literal[
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
]
FormFeldDatenquelle = Literal[
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

# Erlaubte Zeichen fuer form_fields.key/form_groups.key: von Hand vergebene
# Keys (Editor, Schritt 7) muessen lesbar/stabil sein; von Migration 0077
# rueckwirkend erzeugte Keys sind die alte formularfelder.id als UUID-String
# (siehe Migrationsplan) und werden hier NICHT re-validiert (nur bei
# Neuanlage/Aenderung ueber den Editor greift dieses Muster).
_KEY_PATTERN = r"^[a-z][a-z0-9_]*$"


class FormSchemaCreate(BaseModel):
    name: str
    beschreibung: str | None = None


class FormSchemaUpdate(BaseModel):
    name: str | None = None
    beschreibung: str | None = None
    status: FormSchemaStatus | None = None


class FormSchemaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    beschreibung: str | None
    version: int
    status: FormSchemaStatus
    vorgaenger_id: UUID | None
    erstellt_von: UUID | None
    created_at: datetime
    updated_at: datetime


class FormGroupCreate(BaseModel):
    key: str = Field(pattern=_KEY_PATTERN)
    label: dict[str, Any] = {}
    repeatable: bool = True
    min_items: int | None = Field(default=None, ge=0)
    max_items: int | None = Field(default=None, ge=0)
    reihenfolge: int = 0


class FormGroupUpdate(BaseModel):
    label: dict[str, Any] | None = None
    repeatable: bool | None = None
    min_items: int | None = Field(default=None, ge=0)
    max_items: int | None = Field(default=None, ge=0)
    reihenfolge: int | None = None


class FormGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    label: dict[str, Any]
    repeatable: bool
    min_items: int | None
    max_items: int | None
    reihenfolge: int


class FormFieldCreate(BaseModel):
    key: str = Field(pattern=_KEY_PATTERN)
    feld_typ: FormFeldTyp
    label: dict[str, Any] = {}
    hilfetext: str | None = None
    pflichtfeld: bool = False
    validation: dict[str, Any] = {}
    default_value: Any | None = None
    optionen: dict[str, Any] = {}
    group_key: str | None = None
    datenquelle: FormFeldDatenquelle | None = None
    reihenfolge: int = 0


class FormFieldUpdate(BaseModel):
    feld_typ: FormFeldTyp | None = None
    label: dict[str, Any] | None = None
    hilfetext: str | None = None
    pflichtfeld: bool | None = None
    validation: dict[str, Any] | None = None
    default_value: Any | None = None
    optionen: dict[str, Any] | None = None
    group_key: str | None = None
    datenquelle: FormFeldDatenquelle | None = None
    reihenfolge: int | None = None


class FormFieldRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    feld_typ: FormFeldTyp
    label: dict[str, Any]
    hilfetext: str | None
    pflichtfeld: bool
    validation: dict[str, Any]
    default_value: Any | None
    optionen: dict[str, Any]
    group_key: str | None
    datenquelle: FormFeldDatenquelle | None
    reihenfolge: int


class FormViewCreate(BaseModel):
    type: FormViewTyp
    name: str
    konfiguration: dict[str, Any] = {}


class FormViewUpdate(BaseModel):
    name: str | None = None
    konfiguration: dict[str, Any] | None = None


class FormViewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    schema_id: UUID
    type: FormViewTyp
    name: str
    konfiguration: dict[str, Any]
    erstellt_von: UUID | None
    created_at: datetime
    updated_at: datetime


class FormViewFieldLayoutIn(BaseModel):
    field_key: str
    seite: int = Field(default=0, ge=0)
    x_mm: float = Field(default=0, ge=0)
    y_mm: float = Field(default=0, ge=0)
    breite_mm: float = Field(default=85, gt=0)
    hoehe_mm: float = Field(default=8, gt=0)


class FormViewFieldLayoutRead(FormViewFieldLayoutIn):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class FormPresentationElementCreate(BaseModel):
    type: FormPraesentationsTyp
    inhalt: dict[str, Any] = {}
    reihenfolge: int = 0
    seite: int = 0
    x_mm: float | None = None
    y_mm: float | None = None
    breite_mm: float | None = None
    hoehe_mm: float | None = None


class FormPresentationElementUpdate(BaseModel):
    inhalt: dict[str, Any] | None = None
    reihenfolge: int | None = None
    seite: int | None = None
    x_mm: float | None = None
    y_mm: float | None = None
    breite_mm: float | None = None
    hoehe_mm: float | None = None


class FormPresentationElementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: FormPraesentationsTyp
    inhalt: dict[str, Any]
    reihenfolge: int
    seite: int
    x_mm: float | None
    y_mm: float | None
    breite_mm: float | None
    hoehe_mm: float | None


class FormLogicRuleCreate(BaseModel):
    view_id: UUID | None = None
    target_key: str
    effect: FormLogicEffekt
    condition: Any
    value: Any | None = None
    reihenfolge: int = 0


class FormLogicRuleUpdate(BaseModel):
    view_id: UUID | None = None
    target_key: str | None = None
    effect: FormLogicEffekt | None = None
    condition: Any | None = None
    value: Any | None = None
    reihenfolge: int | None = None


class FormLogicRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    view_id: UUID | None
    target_key: str
    effect: FormLogicEffekt
    condition: Any
    value: Any | None
    reihenfolge: int


class FormAuftragstypZuordnungCreate(BaseModel):
    leistungstyp: Leistungstyp
    pflicht_vor_abschluss: bool = False


class FormAuftragstypZuordnungUpdate(BaseModel):
    pflicht_vor_abschluss: bool


class FormAuftragstypZuordnungRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    leistungstyp: Leistungstyp
    pflicht_vor_abschluss: bool


class FormSchemaDetailRead(FormSchemaRead):
    """Vollstaendige Definition inkl. Felder/Gruppen -- fuer den Editor und
    fuer Renderer, die die Struktur einmalig laden statt bei jeder View
    einzeln nachzufragen."""

    groups: list[FormGroupRead] = []
    fields: list[FormFieldRead] = []
    zuordnungen: list[FormAuftragstypZuordnungRead] = []


class FormFieldStateRead(BaseModel):
    visible: bool
    required: bool
    readonly: bool


class FormViewResolvedRead(BaseModel):
    """Eine View vollstaendig aufgeloest fuer den Renderer: Layout/
    Praesentationselemente der View plus (falls eine form_submission
    mitgegeben wurde) die durch form_logic_engine berechneten
    Feld-Zustaende -- Frontend muss die Regeln dafuer nicht selbst kennen,
    kann sie aber bei Bedarf (Live-Eingabe vor dem naechsten Autosave)
    zusaetzlich per formLogicEngine.ts lokal nachrechnen."""

    view: FormViewRead
    layouts: list[FormViewFieldLayoutRead]
    elements: list[FormPresentationElementRead]
    states: dict[str, FormFieldStateRead] = {}


class FormSubmissionStart(BaseModel):
    schema_id: UUID


class FormSubmissionValuesUpdate(BaseModel):
    values: dict[str, Any]


class FormSubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vorgang_id: UUID
    schema_id: UUID
    schema_name: str
    schema_version: int
    values: dict[str, Any]
    status: FormSubmissionStatus
    ausgefuellt_von: UUID | None
    kundensichtbar: bool
    abgeschlossen_am: datetime | None
    created_at: datetime
    updated_at: datetime


class FormSchemaVerfuegbar(BaseModel):
    id: UUID
    name: str
    beschreibung: str | None
    pflicht_vor_abschluss: bool
