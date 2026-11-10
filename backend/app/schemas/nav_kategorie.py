from pydantic import BaseModel, Field


class NavKategorieEintrag(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    reihenfolge: int


class NavKategorienUpdate(BaseModel):
    kategorien: list[NavKategorieEintrag]
    # nav_key -> Kategorie-Name (muss auf einen Eintrag in "kategorien" oben
    # zeigen). Referenz per Name statt id, damit das Frontend beim Anlegen
    # einer neuen Kategorie im selben Speichervorgang keine temporaere id
    # erfinden/aufloesen muss.
    zuordnungen: dict[str, str]


class NavKategorienRead(BaseModel):
    # Leer = Mandant hat die Standardkategorien noch nie angefasst, siehe
    # navSeiten.ts fuer den Fallback.
    kategorien: list[NavKategorieEintrag]
    zuordnungen: dict[str, str]
