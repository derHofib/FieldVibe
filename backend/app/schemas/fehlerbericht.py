from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

FehlerberichtStatus = Literal["neu", "gesichtet", "in_arbeit", "behoben", "abgelehnt", "duplikat"]
FehlerberichtSchweregrad = Literal["niedrig", "mittel", "hoch", "blockierend"]


class FehlerberichtCreate(BaseModel):
    """Kommt als JSON-String im Multipart-Feld "payload" -- mandant_id/user_id
    stammen ausschliesslich aus der Authentifizierung."""

    model_config = ConfigDict(extra="ignore")

    titel: str = Field(min_length=1, max_length=200)
    beschreibung: str = Field(min_length=1, max_length=20000)
    erwartet: str | None = Field(default=None, max_length=20000)
    schritte: str | None = Field(default=None, max_length=20000)
    schweregrad: FehlerberichtSchweregrad
    kontext: dict = Field(default_factory=dict)
    route: str | None = Field(default=None, max_length=1000)
    app_version: str | None = Field(default=None, max_length=100)
    commit_sha: str | None = Field(default=None, max_length=100)


class FehlerberichtCreated(BaseModel):
    id: UUID
    duplikat_von_id: UUID | None


class FehlerberichtListItem(BaseModel):
    id: UUID
    mandant_id: UUID
    mandant_name: str | None
    melder_name: str | None
    titel: str
    schweregrad: FehlerberichtSchweregrad
    status: FehlerberichtStatus
    route: str | None
    app_version: str | None
    commit_sha: str | None
    duplikat_von_id: UUID | None
    hat_screenshot: bool
    erledigt_am: datetime | None
    created_at: datetime
    updated_at: datetime


class FehlerberichtDetail(FehlerberichtListItem):
    beschreibung: str
    erwartet: str | None
    schritte: str | None
    kontext: dict
    screenshot_original_url: str | None
    screenshot_annotiert_url: str | None
    loesungsnotiz: str | None
    fix_commit: str | None
    fix_pr_url: str | None


class FehlerberichtUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: FehlerberichtStatus | None = None
    loesungsnotiz: str | None = Field(default=None, max_length=20000)
    fix_commit: str | None = Field(default=None, max_length=200)
    fix_pr_url: str | None = Field(default=None, max_length=1000)
    duplikat_von_id: UUID | None = None


class FehlerberichtServiceUpdate(BaseModel):
    """Eingeschraenkt fuer die Service-API (Claude): kein duplikat_von_id,
    alles andere ist 422."""

    model_config = ConfigDict(extra="forbid")

    status: FehlerberichtStatus | None = None
    loesungsnotiz: str | None = Field(default=None, max_length=20000)
    fix_commit: str | None = Field(default=None, max_length=200)
    fix_pr_url: str | None = Field(default=None, max_length=1000)


class FehlerberichtZaehler(BaseModel):
    neu: int = 0
    gesichtet: int = 0
    in_arbeit: int = 0
    behoben: int = 0
    abgelehnt: int = 0
    duplikat: int = 0
    gesamt: int = 0
