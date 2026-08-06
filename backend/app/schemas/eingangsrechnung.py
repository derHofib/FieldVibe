from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

_CENT = Decimal("0.01")


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
        return (self.menge * self.einzelpreis).quantize(_CENT)


class EingangsrechnungZahlungCreate(BaseModel):
    betrag: Decimal
    datum: date | None = None


class EingangsrechnungZahlungRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    betrag: Decimal
    datum: date
    erstellt_von: UUID
    created_at: datetime


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
    skonto_prozent: Decimal | None = None
    skonto_tage: int | None = None
    kategorie: str | None = None
    notiz: str | None = None
    positionen: list[EingangsrechnungPositionCreate] = Field(default_factory=list)


class EingangsrechnungUpdate(BaseModel):
    status: str | None = None
    # Nur bei status "entwurf" aenderbar -- siehe app/api/routes/
    # eingangsrechnungen.py: das sind die per E-Mail-Import vorbelegten
    # Platzhalterwerte, die vor der Bestaetigung (Uebergang zu "offen")
    # noch korrigiert werden muessen.
    lieferant_id: UUID | None = None
    lieferant_name: str | None = None
    rechnungsnummer_lieferant: str | None = None
    rechnungsdatum: date | None = None
    betrag_netto: Decimal | None = None
    faellig_am: date | None = None
    skonto_prozent: Decimal | None = None
    skonto_tage: int | None = None
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
    skonto_prozent: Decimal | None
    skonto_tage: int | None
    kategorie: str | None
    status: str
    bezahlt_am: datetime | None
    beleg_object_key: str | None
    notiz: str | None
    erstellt_von: UUID | None
    email_absender: str | None
    email_betreff: str | None
    created_at: datetime
    updated_at: datetime
    positionen: list[EingangsrechnungPositionRead]
    zahlungen: list[EingangsrechnungZahlungRead]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def betrag_brutto(self) -> Decimal:
        return (self.betrag_netto + self.betrag_netto * self.mwst_satz / Decimal("100")).quantize(_CENT)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def bezahlter_betrag(self) -> Decimal:
        return sum((z.betrag for z in self.zahlungen), Decimal("0")).quantize(_CENT)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def offener_betrag(self) -> Decimal:
        return (self.betrag_brutto - self.bezahlter_betrag).quantize(_CENT)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def skonto_frist(self) -> date | None:
        if self.skonto_tage is None:
            return None
        return self.rechnungsdatum + timedelta(days=self.skonto_tage)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def skonto_betrag(self) -> Decimal | None:
        if self.skonto_prozent is None:
            return None
        return (self.betrag_brutto * self.skonto_prozent / Decimal("100")).quantize(_CENT)
