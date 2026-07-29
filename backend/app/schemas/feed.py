from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class FeedCard(BaseModel):
    id: UUID
    vorgangsnummer: str
    titel: str
    kunde_name: str
    anlage_kurzadresse: str | None
    status: str
    leistungstyp: str
    abrechnungsart: str
    prioritaet: int
    last_activity_at: datetime
    letztes_event_vorschau: str | None
    tags: list[str]
    timer_laeuft: bool = False
    dauerauftrag_id: UUID | None = None


class FeedResponse(BaseModel):
    items: list[FeedCard]
    next_cursor: str | None
