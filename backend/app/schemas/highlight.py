from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class HighlightCreate(BaseModel):
    vorgang_event_id: int
    titel: str | None = None


class HighlightRead(BaseModel):
    id: UUID
    vorgang_event_id: int
    titel: str | None
    erstellt_von: UUID
    created_at: datetime
    vorgang_id: UUID
    vorgangsnummer: str
    vorgang_titel: str
    foto_url: str | None
    foto_thumbnail_url: str | None
