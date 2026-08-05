from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

VorgangAbrechnungsart = Literal[
    "pauschale", "aufwand", "festpreis", "wartungsvertrag", "gewaehrleistung"
]
Leistungstyp = Literal["installation", "pruefung", "wartung", "stoerung", "beratung", "planung"]
VorgangStatus = Literal[
    "neu", "geplant", "in_arbeit", "wartet_kunde", "abgeschlossen", "abgerechnet", "storniert"
]
# "abgerechnet" bewusst ausgenommen: dieser Status wird ausschliesslich vom
# Rechnungs-Workflow gesetzt (app/api/routes/rechnungen.py, beim Bezahlen
# einer verknuepften Rechnung), nicht per direktem PATCH auf den Vorgang --
# sonst liesse sich ein Vorgang als abgerechnet markieren, ohne dass je eine
# bezahlte Rechnung dafuer existiert.
VorgangStatusSetzbar = Literal[
    "neu", "geplant", "in_arbeit", "wartet_kunde", "abgeschlossen", "storniert"
]


class VorgangCreate(BaseModel):
    vorgangsnummer: str | None = None
    kunde_id: UUID
    anlage_id: UUID | None = None
    # Weitere Anlagen zusaetzlich zur einzelnen anlage_id (der "Haupt-
    # Anlage") -- v.a. wenn beim Standort mehrere Anlagen automatisch mit
    # in den Vorgang uebernommen werden (siehe app/models/vorgang_anlage.py).
    weitere_anlage_ids: list[UUID] = Field(default_factory=list)
    standort_id: UUID | None = None
    vertrag_id: UUID | None = None
    parent_vorgang_id: UUID | None = None
    titel: str
    beschreibung: str | None = None
    abrechnungsart: VorgangAbrechnungsart
    leistungstyp: Leistungstyp
    prioritaet: int = Field(default=3, ge=1, le=5)
    faelligkeit_am: datetime | None = None
    # Von der Offline-Outbox vergeben (Nacharbeit): macht einen Sync-Retry
    # sicher idempotent, dasselbe Muster wie VorgangEventCreate.client_uuid.
    client_uuid: UUID | None = None


class VorgangAnlagenHinzufuegen(BaseModel):
    anlage_ids: list[UUID]


class VorgangUpdate(BaseModel):
    titel: str | None = None
    beschreibung: str | None = None
    kunde_id: UUID | None = None
    anlage_id: UUID | None = None
    standort_id: UUID | None = None
    vertrag_id: UUID | None = None
    abrechnungsart: VorgangAbrechnungsart | None = None
    leistungstyp: Leistungstyp | None = None
    status: VorgangStatusSetzbar | None = None
    prioritaet: int | None = Field(default=None, ge=1, le=5)
    faelligkeit_am: datetime | None = None
    # Nur zusammen mit status="abgeschlossen" auf einem Vorgang mit
    # leistungstyp="beratung" gueltig: legt einen Folge-Vorgang mit diesem
    # Leistungstyp an, der Kunde/Anlage(n)/Standort sowie die offenen
    # Angebots-Materialbedarfe uebernimmt (siehe close_vorgang).
    folge_leistungstyp: Leistungstyp | None = None


class VorgangRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vorgangsnummer: str
    kunde_id: UUID
    anlage_id: UUID | None
    standort_id: UUID | None
    vertrag_id: UUID | None
    parent_vorgang_id: UUID | None
    dauerauftrag_id: UUID | None
    titel: str
    beschreibung: str | None
    abrechnungsart: VorgangAbrechnungsart
    leistungstyp: Leistungstyp
    status: VorgangStatus
    prioritaet: int
    faelligkeit_am: datetime | None
    last_activity_at: datetime
    abgeschlossen_am: datetime | None
    erstellt_von_kundenportal_zugang_id: UUID | None
    erstellt_von: UUID | None
    created_at: datetime
    updated_at: datetime
    # Nur in der Antwort auf genau die PATCH-Anfrage gesetzt, die diesen
    # Folge-Vorgang erzeugt hat (siehe close_vorgang) -- keine persistierte
    # Spalte, sonst ueberall sonst None.
    folge_vorgang_id: UUID | None = None
