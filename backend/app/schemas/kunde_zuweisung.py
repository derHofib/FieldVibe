from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class KundeZuweisungUpdate(BaseModel):
    """Alter Pfad PUT /{id}/techniker: ersetzt die vollstaendige Menge der
    Betreuer eines Kunden -- einfacher fuer eine Mehrfachauswahl-UI als
    einzelne add/remove-Aufrufe. Der Hauptbetreuer bleibt erhalten, solange er
    in der Liste steht."""

    user_ids: list[UUID]


class BetreuungKurz(BaseModel):
    user_id: UUID
    name: str
    hauptbetreuer: bool


class BetreuerRead(BaseModel):
    user_id: UUID
    name: str
    avatar_url: str | None = None
    hauptbetreuer: bool
    aktiv: bool
    # Sieht diese Person nur Kunden, bei denen sie Betreuer ist (Hinweis im UI:
    # Entfernen kostet sie den Zugriff).
    nur_betreute_kunden: bool
    account_typ_name: str | None = None


class BetreuerKandidat(BaseModel):
    user_id: UUID
    name: str
    avatar_url: str | None = None
    aktiv: bool
    nur_betreute_kunden: bool
    account_typ_name: str | None = None
    anzahl_kunden: int


class KundeBetreuungUpdate(BaseModel):
    """Ersetzt die Betreuung eines Kunden vollstaendig."""

    user_ids: list[UUID]
    hauptbetreuer_id: UUID | None = None


class KundeBetreuungSammel(BaseModel):
    kunde_ids: list[UUID] = Field(min_length=1, max_length=500)
    aktion: Literal["hinzufuegen", "entfernen", "hauptbetreuer"]
    user_id: UUID
    auch_hauptbetreuer: bool = False


class KundeBetreuungSammelErgebnis(BaseModel):
    geaendert: int
