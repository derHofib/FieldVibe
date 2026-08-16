from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PlattformIntegrationCreate(BaseModel):
    typ: str
    config: dict = {}
    secret: str | None = None
    aktiv: bool = True


class PlattformIntegrationUpdate(BaseModel):
    config: dict | None = None
    secret: str | None = None
    aktiv: bool | None = None


class PlattformIntegrationRead(BaseModel):
    id: UUID
    typ: str
    config: dict
    aktiv: bool
    hat_secret: bool
    created_at: datetime
    updated_at: datetime
