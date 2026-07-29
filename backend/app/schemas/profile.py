from app.schemas.anlage import AnlageRead
from app.schemas.kunde import KundeRead
from app.schemas.tag import TagRead
from app.schemas.vorgang import VorgangRead


class KundeProfil(KundeRead):
    anlagen: list[AnlageRead]
    vorgaenge: list[VorgangRead]
    tags: list[TagRead]


class AnlageProfil(AnlageRead):
    kunde: KundeRead
    vorgaenge: list[VorgangRead]
    tags: list[TagRead]
