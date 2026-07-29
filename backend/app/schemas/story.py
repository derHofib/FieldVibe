from typing import Literal
from uuid import UUID

from pydantic import BaseModel

Ampel = Literal["gruen", "gelb", "rot"]


class StoryItem(BaseModel):
    titel: str
    subtitel: str | None = None
    ampel: Ampel | None = None
    ziel_typ: Literal["vorgang", "anlage", "pruefmittel", "material"]
    ziel_id: UUID


class StoriesResponse(BaseModel):
    heute: list[StoryItem]
    fristen: list[StoryItem]
    wartet_kunde: list[StoryItem]
    material: list[StoryItem]
