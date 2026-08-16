from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["super_admin", "mandant_admin", "disponent", "techniker"]


class UserUpdate(BaseModel):
    name: str | None = None
    role: Role | None = None
    aktiv: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mandant_id: UUID | None
    email: str
    role: Role
    name: str
    avatar_url: str | None
    aktiv: bool
    created_at: datetime
    updated_at: datetime
