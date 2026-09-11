from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PlanSymbolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    content_type: str
    url: str
    erstellt_von: UUID | None
    created_at: datetime
    updated_at: datetime


class PlanSymbolUpdate(BaseModel):
    name: str
