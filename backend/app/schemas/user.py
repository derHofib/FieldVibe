from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

Role = Literal["super_admin", "mandant_admin", "disponent", "techniker"]


class UserCreate(BaseModel):
    mandant_id: UUID | None = None
    email: EmailStr
    password: str = Field(min_length=8)
    role: Role
    name: str

    @model_validator(mode="after")
    def _mandant_required_unless_super_admin(self) -> "UserCreate":
        if self.role == "super_admin" and self.mandant_id is not None:
            raise ValueError("super_admin darf keinem Mandanten zugeordnet sein")
        if self.role != "super_admin" and self.mandant_id is None:
            raise ValueError("mandant_id ist für diese Rolle erforderlich")
        return self


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
