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


class RechnungZahlungCreate(BaseModel):
    betrag: Decimal
    datum: date | None = None
    zahlungsart: str | None = None
    notiz: str | None = None


class RechnungZahlungRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    betrag: Decimal
    datum: date
    zahlungsart: str | None
    notiz: str | None
    storniert_zahlung_id: UUID | None
    erstellt_von: UUID
    created_at: datetime


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
    ist_storno: bool
    storniert_rechnung_id: UUID | None
    # Gesetzt, wenn beim Versand eine ZUGFeRD-konforme Hybrid-PDF mit
    # eingebetteter XML erzeugt und archiviert wurde -- siehe
    # rechnung_service._rechnung_dokument_bytes(). NULL bei Entwuerfen,
    # bei deaktivierter E-Rechnung oder wenn Pflichtangaben zum
    # Versand-Zeitpunkt fehlten (stiller Fallback auf normales PDF).
    xml_object_key: str | None
    created_at: datetime
    updated_at: datetime
    positionen: list[RechnungPositionRead]
    zahlungen: list[RechnungZahlungRead] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def betrag_brutto(self) -> Decimal:
        return (self.betrag_netto + self.betrag_netto * self.mwst_satz / Decimal("100")).quantize(Decimal("0.01"))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def bezahlter_betrag(self) -> Decimal:
        return sum((z.betrag for z in self.zahlungen), Decimal("0")).quantize(Decimal("0.01"))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def offener_betrag(self) -> Decimal:
        return (self.betrag_brutto - self.bezahlter_betrag).quantize(Decimal("0.01"))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ist_ueberfaellig(self) -> bool:
        """Faellig, unbezahlt und das Datum ist durch -- die Kennzahl, nach der
        die Uebersicht farblich warnt und der Ueberfaellig-Filter greift.
        Ab teilweise_bezahlt weiterhin ueberfaellig, weil noch Geld aussteht."""
        if self.faellig_am is None or self.status not in ("versendet", "teilweise_bezahlt"):
            return False
        return self.faellig_am < date.today()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def tage_ueberfaellig(self) -> int:
        if not self.ist_ueberfaellig or self.faellig_am is None:
            return 0
        return (date.today() - self.faellig_am).days


class RechnungListe(BaseModel):
    """Antwort der Rechnungsuebersicht. Die Summen beziehen sich bewusst auf
    die komplette gefilterte Menge, nicht auf die ausgelieferte Seite -- eine
    Summenzeile, die nur die ersten 50 Treffer addiert, waere irrefuehrend."""

    eintraege: list[RechnungRead]
    gesamt_anzahl: int
    summe_netto: Decimal
    summe_brutto: Decimal
    summe_offen: Decimal
