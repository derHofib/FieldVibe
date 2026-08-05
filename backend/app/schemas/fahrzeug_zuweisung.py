from uuid import UUID

from pydantic import BaseModel

from app.schemas.anlage import AnlageRead
from app.schemas.user import UserRead


class FahrzeugZuweisungSetzen(BaseModel):
    anlage_id: UUID | None


class FahrzeugZuweisungUebersicht(BaseModel):
    techniker: UserRead
    fahrzeug: AnlageRead | None
