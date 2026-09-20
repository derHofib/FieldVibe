from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class VorgangAbhaengigkeitCreate(BaseModel):
    blockiert_von_id: UUID


class VorgangAbhaengigkeitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vorgang_id: UUID
    blockiert_von_id: UUID
    erstellt_von: UUID | None
    created_at: datetime


class VorgangAbhaengigkeitenListe(BaseModel):
    """Beide Richtungen auf einen Blick, wie es die Vorgang-Detailseite
    braucht: was diesen Vorgang blockiert (blockiert_von) und was dieser
    Vorgang seinerseits blockiert (blockiert)."""

    blockiert_von: list[VorgangAbhaengigkeitRead]
    blockiert: list[VorgangAbhaengigkeitRead]
