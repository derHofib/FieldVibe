from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mandant_id: UUID | None
    actor_user_id: UUID | None
    aktion: str
    entity_type: str | None
    entity_id: UUID | None
    payload: dict
    created_at: datetime
