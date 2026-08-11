from typing import Literal
from uuid import UUID

from pydantic import BaseModel

SearchKategorie = Literal["kunde", "anlage", "vorgang", "rechnung", "tag"]


class SearchHit(BaseModel):
    kategorie: SearchKategorie
    id: UUID
    titel: str
    subtitel: str | None = None


class SearchResponse(BaseModel):
    treffer: list[SearchHit]
