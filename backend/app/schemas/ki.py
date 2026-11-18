from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class KiAnfrageRead(BaseModel):
    client_name: str
    scopes_angefragt: list[str]
    schreiben_erlaubt: bool
    redirect_host: str


class KiAutorisieren(BaseModel):
    anfrage: str = Field(min_length=1)
    scopes: list[str]


class KiAblehnen(BaseModel):
    anfrage: str = Field(min_length=1)


class KiRedirect(BaseModel):
    redirect_url: str


class KiVerbindungRead(BaseModel):
    id: UUID
    client_name: str
    scopes: list[str]
    user_id: UUID
    user_name: str
    erstellt_am: datetime
    zuletzt_genutzt_am: datetime | None
