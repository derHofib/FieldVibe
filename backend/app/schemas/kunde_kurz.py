from uuid import UUID

from pydantic import BaseModel


class KundeKurz(BaseModel):
    id: UUID
    name: str


class RechnungAnKurz(KundeKurz):
    # Verwalter des Empfaengers (z. B. Hausverwaltung einer WEG) fuer die Anzeige "c/o ...".
    verwaltet_von_name: str | None = None
