from pydantic import BaseModel

from app.schemas.kunde import KundeRead
from app.schemas.user import UserRead


class TechnikerZuweisungUebersicht(BaseModel):
    techniker: UserRead
    kunden: list[KundeRead]
