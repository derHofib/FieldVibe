from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

OutboxStatus = Literal["pending", "sending", "sent", "failed"]


class MailOutboxRead(BaseModel):
    """Bewusst ohne Mail-Text: die Uebersicht dient der Fehlersuche, nicht dem Mitlesen."""

    id: UUID
    mandant_id: UUID | None
    email_log_id: UUID | None
    empfaenger: str
    betreff: str
    status: OutboxStatus
    versuche: int
    naechster_versuch_am: datetime
    letzter_fehler: str | None
    anhang_anzahl: int
    created_at: datetime
    gesendet_am: datetime | None
