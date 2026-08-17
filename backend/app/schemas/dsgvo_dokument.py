from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DsgvoDokumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    typ: str
    dateiname: str
    content_type: str
    groesse_bytes: int
    hochgeladen_von: UUID
    created_at: datetime
    updated_at: datetime
