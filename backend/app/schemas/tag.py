from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

TagEntityType = Literal["kunde", "anlage", "vorgang"]


class TagCreate(BaseModel):
    label: str
    farbe: str | None = None


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label: str
    farbe: str | None
    system_tag: bool
    created_at: datetime
    updated_at: datetime


class TagAssignmentCreate(BaseModel):
    entity_type: TagEntityType
    entity_id: UUID


class TagAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tag_id: UUID
    entity_type: TagEntityType
    entity_id: UUID
    created_at: datetime
