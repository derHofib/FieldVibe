from uuid import UUID

from pydantic import BaseModel

from app.schemas.user import UserRead


class KundeZuweisungUpdate(BaseModel):
    """Ersetzt die vollstaendige Menge der einem Kunden zugewiesenen
    Techniker/Disponenten -- einfacher fuer eine Mehrfachauswahl-UI als
    einzelne add/remove-Aufrufe."""

    user_ids: list[UUID]


class KundeMitTechnikern(BaseModel):
    id: UUID
    name: str
    kundennummer: str
    techniker: list[UserRead]
