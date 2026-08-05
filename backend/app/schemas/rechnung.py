from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field


class RechnungPositionCreate(BaseModel):
    beschreibung: str
    menge: Decimal = Decimal("1")
    einheit: str = "Stk"
    einzelpreis: Decimal = Decimal("0")


class RechnungPositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position: int
    beschreibung: str
    menge: Decimal
    einheit: str
    einzelpreis: Decimal

    @computed_field  # type: ignore[prop-decorator]
    @property
    def gesamt(self) -> Decimal:
        return (self.menge * self.einzelpreis).quantize(Decimal("0.01"))


class RechnungCreate(BaseModel):
    kunde_id: UUID
    vorgang_id: UUID | None = None
    # betrag_netto bleibt der einfache Weg fuer eine einzelne Abschlussrechnung
    # ohne eigene Positionen (unveraendertes Verhalten aus Phase 6). Werden
    # positionen mitgegeben, wird betrag_netto beim Lesen durch deren Summe
    # ersetzt -- fuer Teil-/Sammelrechnungen mit eigenen Zeilen.
    betrag_netto: Decimal = Decimal("0")
    mwst_satz: Decimal = Decimal("19.00")
    faellig_am: date | None = None
    # Zeitpunkt der Leistung/Lieferung (§14 Abs. 4 Nr. 6 UStG) -- optional,
    # da oft identisch mit dem Rechnungsdatum.
    leistungsdatum: date | None = None
    positionen: list[RechnungPositionCreate] = Field(default_factory=list)


class RechnungUpdate(BaseModel):
    status: str | None = None
    betrag_netto: Decimal | None = None
    faellig_am: date | None = None
    leistungsdatum: date | None = None


class RechnungRead(BaseModel):
    id: UUID
    kunde_id: UUID
    vorgang_id: UUID | None
    rechnungsnummer: str
    betrag_netto: Decimal
    mwst_satz: Decimal
    status: str
    faellig_am: date | None
    leistungsdatum: date | None
    erstellt_von: UUID
    versendet_am: datetime | None
    bezahlt_am: datetime | None
    mahnstufe: int
    letzte_mahnung_am: datetime | None
    created_at: datetime
    updated_at: datetime
    positionen: list[RechnungPositionRead]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def betrag_brutto(self) -> Decimal:
        return (self.betrag_netto + self.betrag_netto * self.mwst_satz / Decimal("100")).quantize(Decimal("0.01"))
