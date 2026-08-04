from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PapierkorbEintragRead(BaseModel):
    entity_typ: str
    id: UUID
    titel: str | None
    geloescht_am: datetime
    geloescht_von: UUID | None
    geloescht_von_name: str | None
