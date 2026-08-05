from pydantic import BaseModel, Field


class MandantEinstellungenRead(BaseModel):
    scheduler_stunde_utc: int | None
    effektive_scheduler_stunde_utc: int


class MandantEinstellungenUpdate(BaseModel):
    # None setzt explizit auf den globalen Default zurueck -- einziges Feld
    # dieser Ressource, daher kein exclude_unset-Partial-Update noetig.
    scheduler_stunde_utc: int | None = Field(default=None, ge=0, le=23)
