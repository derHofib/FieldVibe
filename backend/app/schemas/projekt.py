from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

ProjektAufgabePrioritaet = Literal["niedrig", "mittel", "hoch"]


class ChecklistenPunkt(BaseModel):
    text: str
    erledigt: bool = False


class ProjektCreate(BaseModel):
    name: str
    beschreibung: str | None = None


class ProjektUpdate(BaseModel):
    name: str | None = None
    beschreibung: str | None = None
    archiviert: bool | None = None


class ProjektRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    beschreibung: str | None
    archiviert: bool
    erstellt_von: UUID
    created_at: datetime
    updated_at: datetime


class ProjektSpalteCreate(BaseModel):
    name: str


class ProjektSpalteUpdate(BaseModel):
    name: str | None = None
    reihenfolge: int | None = None


class ProjektSpalteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    projekt_id: UUID
    name: str
    reihenfolge: int


class ProjektAufgabeCreate(BaseModel):
    projekt_id: UUID
    spalte_id: UUID
    titel: str
    beschreibung: str | None = None
    faelligkeit_am: date | None = None
    prioritaet: ProjektAufgabePrioritaet = "mittel"
    zugewiesen_an: UUID | None = None
    vorgang_id: UUID | None = None
    checkliste: list[ChecklistenPunkt] = []
    zusatzfelder: dict[str, str] = {}


class ProjektAufgabeUpdate(BaseModel):
    spalte_id: UUID | None = None
    titel: str | None = None
    beschreibung: str | None = None
    faelligkeit_am: date | None = None
    prioritaet: ProjektAufgabePrioritaet | None = None
    zugewiesen_an: UUID | None = None
    vorgang_id: UUID | None = None
    checkliste: list[ChecklistenPunkt] | None = None
    zusatzfelder: dict[str, str] | None = None


class ProjektAufgabeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    projekt_id: UUID
    spalte_id: UUID
    titel: str
    beschreibung: str | None
    faelligkeit_am: date | None
    prioritaet: ProjektAufgabePrioritaet
    zugewiesen_an: UUID | None
    vorgang_id: UUID | None
    checkliste: list[ChecklistenPunkt]
    zusatzfelder: dict[str, str]
    erstellt_von: UUID
    created_at: datetime
    updated_at: datetime


class ProjektAufgabeMitDetails(ProjektAufgabeRead):
    """Angereicherte Fassung fuer das Kanban-Board und die "Verknuepfte
    Aufgaben"-Ansicht am Vorgang -- erspart dem Frontend N+1-Lookups fuer
    Namen, die es ohnehin sofort anzeigen muss."""

    zugewiesener_name: str | None = None
    vorgang_vorgangsnummer: str | None = None
    vorgang_kunde_name: str | None = None
