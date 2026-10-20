from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ImportEntitaet = Literal["kunden", "anlagen", "material"]
ImportModus = Literal["gueltige", "alles_oder_nichts"]
DublettenAktion = Literal["ueberspringen", "aktualisieren", "anlegen"]
ZeilenStatus = Literal["neu", "warnung", "dublette", "fehler"]
ZeilenAktion = Literal["anlegen", "aktualisieren", "ueberspringen", "keine"]


class ImportKonfiguration(BaseModel):
    """Zuordnung (Feld -> Spaltenindex der Datei, null = nicht importieren) und Optionen.
    Probelauf und Import erhalten dieselbe Konfiguration; der Import prueft ihren Hash."""

    mapping: dict[str, int | None]
    modus: ImportModus = "gueltige"
    chargengroesse: int = Field(default=200, ge=10, le=1000)
    # Aktion je Dublettenart; fehlende Arten gelten als "ueberspringen".
    dubletten_aktionen: dict[str, DublettenAktion] = Field(default_factory=dict)


class ImportSpalte(BaseModel):
    index: int
    name: str
    beispiele: list[str]


class ImportFeld(BaseModel):
    key: str
    label: str
    pflicht: bool
    gruppe: str | None
    hinweis: str | None


class ImportVorschlag(BaseModel):
    feld: str
    spalte: int | None
    sicherheit: Literal["sicher", "vermutet"] | None


class ImportDublettenArt(BaseModel):
    key: str
    label: str
    aktionen: list[DublettenAktion]
    standard: DublettenAktion


class ImportAnalyse(BaseModel):
    import_lauf_id: UUID
    entitaet: ImportEntitaet
    dateiname: str
    format: Literal["csv", "xlsx"]
    trennzeichen: str | None
    kodierung: str | None
    blatt: str | None
    blaetter: list[str]
    zeilen_gesamt: int
    spalten: list[ImportSpalte]
    felder: list[ImportFeld]
    vorschlag: list[ImportVorschlag]
    dubletten_arten: list[ImportDublettenArt]
    pflicht_hinweis: str


class ImportZeile(BaseModel):
    zeile: int
    status: ZeilenStatus
    aktion: ZeilenAktion
    meldungen: list[str]
    vorschau: dict[str, str]
    dublette_art: str | None
    dublette_von: str | None


class ImportZusammenfassung(BaseModel):
    gesamt: int
    neu: int
    warnung: int
    dublette: int
    fehler: int
    anlegen: int
    aktualisieren: int
    ueberspringen: int


class ImportErgebnis(BaseModel):
    import_lauf_id: UUID
    status: str
    zusammenfassung: ImportZusammenfassung
    zeilen: list[ImportZeile]
    zeilen_gekuerzt: bool
    abbruch: str | None = None
    fehlerbericht_verfuegbar: bool


class ImportLaufRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entitaet: ImportEntitaet
    dateiname: str
    sha256: str
    dateigroesse: int
    format: str
    status: str
    zeilen_gesamt: int
    zeilen_neu: int
    zeilen_aktualisiert: int
    zeilen_uebersprungen: int
    zeilen_fehler: int
    zeilen_warnungen: int
    ergebnis: dict | None
    erstellt_von: UUID
    created_at: datetime
    geprueft_am: datetime | None
    ausgefuehrt_am: datetime | None
    abgeschlossen_am: datetime | None
    rueckgaengig_am: datetime | None
    kann_rueckgaengig: bool = False
    fehlerbericht_verfuegbar: bool = False
    quelle_verfuegbar: bool = False
