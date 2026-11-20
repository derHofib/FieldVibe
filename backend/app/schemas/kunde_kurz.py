from uuid import UUID

from pydantic import BaseModel


class KundeKurz(BaseModel):
    id: UUID
    name: str
