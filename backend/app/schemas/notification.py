from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

NotificationTyp = Literal["mention", "frist", "zuweisung", "angebot", "anfrage"]


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    typ: NotificationTyp
    titel: str
    ref_entity_type: str | None
    ref_entity_id: UUID | None
    gelesen_am: datetime | None
    created_at: datetime
