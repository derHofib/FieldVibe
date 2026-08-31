from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

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
    # projekt_id=None -> private Aufgabe (siehe app/models/projekt.py).
    # spalte_id ist dann zwingend ebenfalls None (ck_projekt_aufgaben_
    # spalte_erfordert_projekt).
    projekt_id: UUID | None = None
    spalte_id: UUID | None = None
    eltern_aufgabe_id: UUID | None = None
    titel: str
    beschreibung: str | None = None
    faelligkeit_am: date | None = None
    prioritaet: ProjektAufgabePrioritaet = "mittel"
    zugewiesen_an: UUID | None = None
    vorgang_id: UUID | None = None
    anlage_id: UUID | None = None
    kunde_id: UUID | None = None
    standort_id: UUID | None = None
    checkliste: list[ChecklistenPunkt] = []
    zusatzfelder: dict[str, str] = {}

    @model_validator(mode="after")
    def _spalte_erfordert_projekt(self) -> "ProjektAufgabeCreate":
        if self.spalte_id is not None and self.projekt_id is None:
            raise ValueError("spalte_id setzt projekt_id voraus")
        return self


class ProjektAufgabeUpdate(BaseModel):
    # projekt_id ist absichtlich nicht aenderbar -- eine Aufgabe wechselt
    # nach dem Anlegen nicht zwischen "privat" und "Kanban" oder zwischen
    # Projekten, das vermeidet Sonderfaelle beim Rechte-/Spalten-Check.
    spalte_id: UUID | None = None
    eltern_aufgabe_id: UUID | None = None
    titel: str | None = None
    beschreibung: str | None = None
    faelligkeit_am: date | None = None
    prioritaet: ProjektAufgabePrioritaet | None = None
    zugewiesen_an: UUID | None = None
    erledigt: bool | None = None
    vorgang_id: UUID | None = None
    anlage_id: UUID | None = None
    kunde_id: UUID | None = None
    standort_id: UUID | None = None
    checkliste: list[ChecklistenPunkt] | None = None
    zusatzfelder: dict[str, str] | None = None


class ProjektAufgabeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    projekt_id: UUID | None
    spalte_id: UUID | None
    eltern_aufgabe_id: UUID | None
    titel: str
    beschreibung: str | None
    faelligkeit_am: date | None
    prioritaet: ProjektAufgabePrioritaet
    zugewiesen_an: UUID | None
    erledigt_am: datetime | None
    vorgang_id: UUID | None
    anlage_id: UUID | None
    kunde_id: UUID | None
    standort_id: UUID | None
    checkliste: list[ChecklistenPunkt]
    zusatzfelder: dict[str, str]
    erstellt_von: UUID
    created_at: datetime
    updated_at: datetime


class ProjektAufgabeMitDetails(ProjektAufgabeRead):
    """Angereicherte Fassung fuer das Kanban-Board, die "Meine Aufgaben"-
    Liste und die "Verknuepfte Aufgaben"-Ansicht an Vorgang/Anlage/Kunde/
    Standort -- erspart dem Frontend N+1-Lookups fuer Namen, die es ohnehin
    sofort anzeigen muss."""

    zugewiesener_name: str | None = None
    vorgang_vorgangsnummer: str | None = None
    vorgang_kunde_name: str | None = None
    anlage_name: str | None = None
    kunde_name: str | None = None
    standort_name: str | None = None
    unteraufgaben_gesamt: int = 0
    unteraufgaben_erledigt: int = 0
