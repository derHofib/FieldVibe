from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TerminCreate(BaseModel):
    vorgang_id: UUID
    techniker_id: UUID
    titel: str
    start_at: datetime
    ende_at: datetime
    notiz: str | None = None
    fahrzeit_minuten: int | None = Field(default=None, ge=0)
    pause_minuten: int | None = Field(default=None, ge=0)

    @field_validator("titel")
    @classmethod
    def _titel_nicht_leer(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Titel darf nicht leer sein")
        return v

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
    fahrzeit_minuten: int | None = Field(default=None, ge=0)
    pause_minuten: int | None = Field(default=None, ge=0)

    @field_validator("titel")
    @classmethod
    def _titel_nicht_leer(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Titel darf nicht leer sein")
        return v


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
