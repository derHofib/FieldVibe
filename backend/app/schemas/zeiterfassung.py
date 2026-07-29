from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ZeiterfassungStart(BaseModel):
    vorgang_id: UUID
    taetigkeit: str | None = None
    abrechenbar: bool = True


class ZeiterfassungRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vorgang_id: UUID
    techniker_id: UUID
    start_at: datetime
    ende_at: datetime | None
    taetigkeit: str | None
    abrechenbar: bool
    freigegeben: bool
    created_at: datetime
    updated_at: datetime
