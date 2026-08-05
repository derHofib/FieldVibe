from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class MandantIntegrationCreate(BaseModel):
    typ: str
    config: dict = {}
    secret: str | None = None
    aktiv: bool = True


class MandantIntegrationUpdate(BaseModel):
    config: dict | None = None
    secret: str | None = None
    aktiv: bool | None = None


class MandantIntegrationRead(BaseModel):
    id: UUID
    mandant_id: UUID
    typ: str
    config: dict
    aktiv: bool
    hat_secret: bool
    created_at: datetime
    updated_at: datetime
