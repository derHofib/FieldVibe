from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class TerminCreate(BaseModel):
    vorgang_id: UUID
    techniker_id: UUID
    titel: str
    start_at: datetime
    ende_at: datetime
    notiz: str | None = None
    fahrzeit_minuten: int | None = None
    pause_minuten: int | None = None

    @model_validator(mode="after")
    def _check_zeitraum(self) -> "TerminCreate":
        if self.ende_at <= self.start_at:
            raise ValueError("ende_at muss nach start_at liegen")
        return self


class TerminUpdate(BaseModel):
    titel: str | None = None
    techniker_id: UUID | None = None
    start_at: datetime | None = None
    ende_at: datetime | None = None
    status: str | None = None
    notiz: str | None = None
    fahrzeit_minuten: int | None = None
    pause_minuten: int | None = None


class TerminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vorgang_id: UUID
    techniker_id: UUID
    erstellt_von: UUID
    titel: str
    start_at: datetime
    ende_at: datetime
    status: str
    notiz: str | None
    fahrzeit_minuten: int | None
    pause_minuten: int | None
    created_at: datetime
    updated_at: datetime


class TerminWarnung(BaseModel):
    typ: str
    meldung: str
    anderer_termin_id: UUID


class TerminCreateResult(BaseModel):
    termin: TerminRead
    warnungen: list[TerminWarnung]
