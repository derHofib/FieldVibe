from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

EventType = Literal[
    "kommentar",
    "status_change",
    "foto",
    "dokument",
    "mangel",
    "angebot",
    "material",
    "zeit_start",
    "zeit_stop",
    "termin",
    "rechnung_status",
    "system",
    "unterschrift",
    "eingangsrechnung_status",
    "formular",
    "leistung",
]


class VorgangEventCreate(BaseModel):
    event_type: EventType
    body: str | None = None
    payload: dict = {}
    ref_entity_type: str | None = None
    ref_entity_id: UUID | None = None
    kundensichtbar: bool = False
    client_uuid: UUID | None = None


class VorgangEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vorgang_id: UUID
    event_type: EventType
    author_user_id: UUID | None
    is_system: bool
    kundensichtbar: bool
    body: str | None
    payload: dict
    ref_entity_type: str | None
    ref_entity_id: UUID | None
    client_uuid: UUID | None
    created_at: datetime
    # Nur bei event_type == "foto"/"unterschrift"/"dokument" gesetzt: bei
    # jedem Lesen frisch aus dem in payload gespeicherten S3-Key signiert
    # (presigned URLs laufen ab, koennen also nicht einfach mitgespeichert
    # werden).
    foto_url: str | None = None
    foto_thumbnail_url: str | None = None
    unterschrift_url: str | None = None
    dokument_url: str | None = None
    dokument_dateiname: str | None = None
