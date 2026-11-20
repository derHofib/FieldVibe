from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

SearchKategorie = Literal[
    "kunde", "anlage", "vorgang", "rechnung", "angebot", "auftrag", "projekt", "telefonat", "tag"
]


class SearchHit(BaseModel):
    kategorie: SearchKategorie
    id: UUID
    titel: str
    subtitel: str | None = None
    nummer: str | None = None
    status: str | None = None
    kunde_name: str | None = None
    betrag: Decimal | None = None
    datum: date | None = None
    zusatz: str | None = None


class SearchResponse(BaseModel):
    treffer: list[SearchHit]
    # Gesamtzahl je durchsuchter Kategorie (ohne limit/offset), gedeckelt.
    anzahl: dict[str, int] = {}
