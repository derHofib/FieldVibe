from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field


class EingangsrechnungPositionCreate(BaseModel):
    beschreibung: str
    menge: Decimal = Decimal("1")
    einheit: str = "Stk"
    einzelpreis: Decimal = Decimal("0")


class EingangsrechnungPositionRead(BaseModel):
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


class EingangsrechnungCreate(BaseModel):
    lieferant_id: UUID | None = None
    # Pflicht, wenn lieferant_id fehlt (Aussteller ohne eigenen Lieferanten-
    # Stammdatensatz) -- ist lieferant_id gesetzt, wird der Name serverseitig
    # aus dem Lieferanten-Datensatz uebernommen und dieses Feld ignoriert.
    lieferant_name: str | None = None
    vorgang_id: UUID | None = None
    rechnungsnummer_lieferant: str
    rechnungsdatum: date
    faellig_am: date | None = None
    betrag_netto: Decimal = Decimal("0")
    mwst_satz: Decimal = Decimal("19.00")
    kategorie: str | None = None
    notiz: str | None = None
    positionen: list[EingangsrechnungPositionCreate] = Field(default_factory=list)


class EingangsrechnungUpdate(BaseModel):
    status: str | None = None
    betrag_netto: Decimal | None = None
    faellig_am: date | None = None
    kategorie: str | None = None
    notiz: str | None = None


class EingangsrechnungRead(BaseModel):
    id: UUID
    lieferant_id: UUID | None
    lieferant_name: str
    vorgang_id: UUID | None
    rechnungsnummer_lieferant: str
    rechnungsdatum: date
    eingegangen_am: date
    faellig_am: date | None
    betrag_netto: Decimal
    mwst_satz: Decimal
    kategorie: str | None
    status: str
    bezahlt_am: datetime | None
    beleg_object_key: str | None
    notiz: str | None
    erstellt_von: UUID
    created_at: datetime
    updated_at: datetime
    positionen: list[EingangsrechnungPositionRead]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def betrag_brutto(self) -> Decimal:
        return (self.betrag_netto + self.betrag_netto * self.mwst_satz / Decimal("100")).quantize(Decimal("0.01"))
