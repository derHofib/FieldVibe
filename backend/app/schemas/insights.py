from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class TechnikerAuslastung(BaseModel):
    techniker_id: UUID
    name: str
    stunden_diese_woche: Decimal


class Insights(BaseModel):
    vorgaenge_nach_status: dict[str, int]
    offene_rechnungssumme: Decimal
    offene_verbindlichkeiten: Decimal
    angebote_versendet: int
    angebote_angenommen: int
    angebote_annahmequote: float | None
    techniker_auslastung: list[TechnikerAuslastung]
