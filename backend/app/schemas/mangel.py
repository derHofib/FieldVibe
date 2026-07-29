from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MangelCreate(BaseModel):
    vorgang_id: UUID
    anlage_id: UUID | None = None
    beschreibung: str
    schweregrad: str = "mittel"


class MangelUpdate(BaseModel):
    beschreibung: str | None = None
    schweregrad: str | None = None
    status: str | None = None


class MangelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vorgang_id: UUID
    anlage_id: UUID | None
    beschreibung: str
    schweregrad: str
    status: str
    gemeldet_von: UUID
    angebot_id: UUID | None
    reparatur_vorgang_id: UUID | None
    behoben_am: datetime | None
    created_at: datetime
    updated_at: datetime
