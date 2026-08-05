from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

EmailEntityTyp = Literal["kunde", "vorgang", "angebot", "rechnung", "bestellung"]
EmailStatus = Literal["gesendet", "fehler"]


class EmailSenden(BaseModel):
    empfaenger: EmailStr
    betreff: str
    inhalt: str


class EmailMitAnhangSenden(BaseModel):
    """Fuer den Versand eines Angebots/einer Rechnung/Bestellung als PDF --
    betreff/inhalt sind optional, der Router setzt sinnvolle Standardtexte,
    wenn sie fehlen (siehe app/api/routes/angebote.py etc.)."""

    empfaenger: EmailStr
    betreff: str | None = None
    inhalt: str | None = None


class EmailLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_type: EmailEntityTyp
    entity_id: UUID
    empfaenger: str
    betreff: str
    inhalt: str
    anhang_dateiname: str | None
    status: EmailStatus
    fehlermeldung: str | None
    gesendet_von: UUID
    created_at: datetime
