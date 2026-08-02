from decimal import Decimal

from app.schemas.anlage import AnlageRead
from app.schemas.kunde import KundeRead
from app.schemas.standort import StandortRead
from app.schemas.tag import TagRead
from app.schemas.user import UserRead
from app.schemas.vorgang import VorgangRead


class KundeProfil(KundeRead):
    anlagen: list[AnlageRead]
    vorgaenge: list[VorgangRead]
    tags: list[TagRead]
    techniker: list[UserRead]


class AnlageProfil(AnlageRead):
    kunde: KundeRead | None
    vorgaenge: list[VorgangRead]
    tags: list[TagRead]
    vorgaenge_nach_status: dict[str, int]
    zeiterfassung_stunden_gesamt: Decimal


class StandortProfil(StandortRead):
    kunde: KundeRead | None
    anlagen: list[AnlageRead]
    vorgaenge: list[VorgangRead]
    vorgaenge_nach_status: dict[str, int]
