from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

KennzahlEinheit = Literal["anzahl", "eur", "tage", "prozent", "minuten"]
# stand = Momentaufnahme heute, von/bis werden ignoriert
KennzahlArt = Literal["zeitraum", "stand"]
Darstellung = Literal["zahl", "zahl_verlauf", "saeulen", "linie", "balken", "ring", "tabelle"]
WidgetGroesse = Literal["s", "m", "l", "xl"]
DashboardZeitraum = Literal["woche", "monat", "quartal", "jahr", "12_monate"]


class KennzahlGruppierung(BaseModel):
    schluessel: str
    label: str
    zeit: bool


class KennzahlDef(BaseModel):
    schluessel: str
    titel: str
    beschreibung: str
    bereich: Literal["vorgaenge", "finanzen", "sales", "telefonate"]
    einheit: KennzahlEinheit
    art: KennzahlArt
    summierbar: bool
    gruppierungen: list[KennzahlGruppierung]


class KennzahlZeile(BaseModel):
    schluessel: str
    label: str
    wert: float | None
    vorperiode: float | None = None


class KennzahlDaten(BaseModel):
    kennzahl: str
    einheit: KennzahlEinheit
    art: KennzahlArt
    gruppierung: str  # "gesamt", wenn nicht aufgeteilt
    von: date | None
    bis: date | None
    gesamt: float | None
    vorperiode_gesamt: float | None
    zeilen: list[KennzahlZeile]
    abgeschnitten: bool
    datumsbezug: str | None


class DashboardWidget(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    kennzahl: str = Field(pattern=r"^[a-z_]+\.[a-z_]+$", max_length=64)
    darstellung: Darstellung
    gruppierung: str | None = Field(default=None, pattern=r"^[a-z_]+$", max_length=32)
    groesse: WidgetGroesse
    titel: str | None = Field(default=None, max_length=80)
    vergleich: bool = True


class DashboardLayout(BaseModel):
    zeitraum: DashboardZeitraum = "monat"
    widgets: list[DashboardWidget] = Field(default_factory=list, max_length=30)


DashboardName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class DashboardAnlegen(BaseModel):
    name: DashboardName
    layout: DashboardLayout
    vorlage: str | None = Field(default=None, max_length=32)
    fuer_alle: bool = False


class DashboardAendern(BaseModel):
    name: DashboardName | None = None
    layout: DashboardLayout | None = None
    fuer_alle: bool | None = None


class DashboardReihenfolge(BaseModel):
    ids: list[UUID] = Field(max_length=100)


class DashboardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    layout: DashboardLayout
    fuer_alle: bool
    vorlage: str | None
    sortierung: int
    eigenes: bool
    ersteller_name: str
    updated_at: datetime
