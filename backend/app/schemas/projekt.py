from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ProjektAufgabePrioritaet = Literal["niedrig", "mittel", "hoch"]
ProjektAufgabeTyp = Literal["aufgabe", "phase", "schritt", "meilenstein"]
ZeitplanTyp = Literal["phase", "schritt", "meilenstein"]
VerschiebeModus = Literal["bei_konflikt", "immer"]
AbhaengigkeitArt = Literal["ende_anfang", "anfang_anfang", "ende_ende"]


class ChecklistenPunkt(BaseModel):
    text: str
    erledigt: bool = False


class ProjektCreate(BaseModel):
    name: str
    beschreibung: str | None = None
    vertrag_id: UUID | None = None


class ProjektUpdate(BaseModel):
    name: str | None = None
    beschreibung: str | None = None
    archiviert: bool | None = None
    vertrag_id: UUID | None = None


class ProjektRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    beschreibung: str | None
    archiviert: bool
    vertrag_id: UUID | None
    erstellt_von: UUID
    created_at: datetime
    updated_at: datetime


class ProjektSpalteCreate(BaseModel):
    name: str


class ProjektSpalteUpdate(BaseModel):
    name: str | None = None
    reihenfolge: int | None = None


class ProjektSpalteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    projekt_id: UUID
    name: str
    reihenfolge: int


class ProjektAufgabeCreate(BaseModel):
    # projekt_id=None -> private Aufgabe (siehe app/models/projekt.py).
    # spalte_id ist dann zwingend ebenfalls None (ck_projekt_aufgaben_
    # spalte_erfordert_projekt).
    projekt_id: UUID | None = None
    spalte_id: UUID | None = None
    eltern_aufgabe_id: UUID | None = None
    titel: str
    beschreibung: str | None = None
    faelligkeit_am: date | None = None
    prioritaet: ProjektAufgabePrioritaet = "mittel"
    zugewiesen_an: UUID | None = None
    vorgang_id: UUID | None = None
    anlage_id: UUID | None = None
    kunde_id: UUID | None = None
    standort_id: UUID | None = None
    checkliste: list[ChecklistenPunkt] = []
    zusatzfelder: dict[str, str] = {}

    @model_validator(mode="after")
    def _spalte_erfordert_projekt(self) -> "ProjektAufgabeCreate":
        if self.spalte_id is not None and self.projekt_id is None:
            raise ValueError("spalte_id setzt projekt_id voraus")
        return self


class ProjektAufgabeUpdate(BaseModel):
    # projekt_id ist absichtlich nicht aenderbar -- eine Aufgabe wechselt
    # nach dem Anlegen nicht zwischen "privat" und "Kanban" oder zwischen
    # Projekten, das vermeidet Sonderfaelle beim Rechte-/Spalten-Check.
    spalte_id: UUID | None = None
    eltern_aufgabe_id: UUID | None = None
    titel: str | None = None
    beschreibung: str | None = None
    faelligkeit_am: date | None = None
    prioritaet: ProjektAufgabePrioritaet | None = None
    zugewiesen_an: UUID | None = None
    erledigt: bool | None = None
    vorgang_id: UUID | None = None
    anlage_id: UUID | None = None
    kunde_id: UUID | None = None
    standort_id: UUID | None = None
    checkliste: list[ChecklistenPunkt] | None = None
    zusatzfelder: dict[str, str] | None = None


class ProjektAufgabeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    projekt_id: UUID | None
    spalte_id: UUID | None
    eltern_aufgabe_id: UUID | None
    titel: str
    beschreibung: str | None
    faelligkeit_am: date | None
    prioritaet: ProjektAufgabePrioritaet
    zugewiesen_an: UUID | None
    erledigt_am: datetime | None
    vorgang_id: UUID | None
    anlage_id: UUID | None
    kunde_id: UUID | None
    standort_id: UUID | None
    checkliste: list[ChecklistenPunkt]
    zusatzfelder: dict[str, str]
    typ: ProjektAufgabeTyp
    start_am: date | None
    ende_am: date | None
    fortschritt: int
    erstellt_von: UUID
    created_at: datetime
    updated_at: datetime


class ProjektAufgabeMitDetails(ProjektAufgabeRead):
    """Angereicherte Fassung fuer das Kanban-Board, die "Meine Aufgaben"-
    Liste und die "Verknuepfte Aufgaben"-Ansicht an Vorgang/Anlage/Kunde/
    Standort -- erspart dem Frontend N+1-Lookups fuer Namen, die es ohnehin
    sofort anzeigen muss."""

    zugewiesener_name: str | None = None
    vorgang_vorgangsnummer: str | None = None
    vorgang_kunde_name: str | None = None
    anlage_name: str | None = None
    kunde_name: str | None = None
    standort_name: str | None = None
    unteraufgaben_gesamt: int = 0
    unteraufgaben_erledigt: int = 0


class ZeitplanVorgangRef(BaseModel):
    id: UUID
    vorgangsnummer: str
    titel: str
    status: str


class ZeitplanTerminRef(BaseModel):
    id: UUID
    start: datetime
    ende: datetime | None
    techniker_name: str | None


class ZeitplanBestellungRef(BaseModel):
    id: UUID
    bestellnummer: str
    status: str
    liefertermin: date | None
    lieferant_name: str | None


class ZeitplanPartnerRef(BaseModel):
    id: UUID
    name: str


class ZeitplanElement(BaseModel):
    id: UUID
    typ: ZeitplanTyp
    titel: str
    phase_id: UUID | None
    start_am: date | None
    ende_am: date | None
    fortschritt: int
    plan_reihenfolge: int
    zugewiesen_an: UUID | None
    zugewiesen_name: str | None
    erledigt: bool
    vorgang: ZeitplanVorgangRef | None = None
    termine: list[ZeitplanTerminRef] = Field(default_factory=list)
    bestellung: ZeitplanBestellungRef | None = None
    # True = start_am/ende_am kommen aus dem Liefertermin der Bestellung und
    # sind nicht direkt editierbar.
    datum_gesperrt: bool = False
    partner: ZeitplanPartnerRef | None = None
    # Kritischer Pfad (berechnet): null = ohne Datum bzw. Phase.
    puffer_tage: int | None = None
    kritisch: bool = False
    # Nur mit ?basisplan_id=: Soll-Termine und Abweichung des Endes in Tagen
    # (positiv = spaeter als geplant).
    basis_start_am: date | None = None
    basis_ende_am: date | None = None
    abweichung_tage: int | None = None


class ZeitplanAbhaengigkeit(BaseModel):
    id: UUID
    vorgaenger_id: UUID
    nachfolger_id: UUID
    art: AbhaengigkeitArt
    versatz_tage: int
    kritisch: bool = False


class ZeitplanRead(BaseModel):
    projekt_id: UUID
    verschiebe_modus: VerschiebeModus
    elemente: list[ZeitplanElement]
    abhaengigkeiten: list[ZeitplanAbhaengigkeit]


class ZeitplanElementCreate(BaseModel):
    typ: ZeitplanTyp
    titel: str
    phase_id: UUID | None = None
    start_am: date | None = None
    ende_am: date | None = None
    zugewiesen_an: UUID | None = None
    vorgang_id: UUID | None = None
    bestellung_id: UUID | None = None
    partner_id: UUID | None = None


class ZeitplanElementUpdate(BaseModel):
    # titel/fortschritt/plan_reihenfolge sind nicht null-bar -- ein explizites
    # null wird ueber den Validator abgelehnt statt still ignoriert.
    titel: str | None = None
    start_am: date | None = None
    ende_am: date | None = None
    fortschritt: int | None = Field(default=None, ge=0, le=100)
    phase_id: UUID | None = None
    plan_reihenfolge: int | None = None
    zugewiesen_an: UUID | None = None
    # null = Verknuepfung loesen (nur ueber model_fields_set unterscheidbar).
    vorgang_id: UUID | None = None
    bestellung_id: UUID | None = None
    partner_id: UUID | None = None

    @model_validator(mode="after")
    def _keine_null_werte(self) -> "ZeitplanElementUpdate":
        for feld in ("titel", "fortschritt", "plan_reihenfolge"):
            if feld in self.model_fields_set and getattr(self, feld) is None:
                raise ValueError(f"{feld} darf nicht null sein")
        return self


class ZeitplanAbhaengigkeitCreate(BaseModel):
    vorgaenger_id: UUID
    nachfolger_id: UUID
    art: AbhaengigkeitArt = "ende_anfang"
    versatz_tage: int = Field(default=0, ge=-3650, le=3650)


class ZeitplanAbhaengigkeitUpdate(BaseModel):
    art: AbhaengigkeitArt | None = None
    versatz_tage: int | None = Field(default=None, ge=-3650, le=3650)

    @model_validator(mode="after")
    def _mindestens_ein_feld(self) -> "ZeitplanAbhaengigkeitUpdate":
        if self.art is None and self.versatz_tage is None:
            raise ValueError("art oder versatz_tage angeben")
        return self


class ZeitplanEinstellungenUpdate(BaseModel):
    verschiebe_modus: VerschiebeModus


class ZeitplanVorgangAuswahl(BaseModel):
    id: UUID
    vorgangsnummer: str
    titel: str
    status: str
    gehoert_zum_projekt: bool


class ZeitplanBestellungAuswahl(BaseModel):
    id: UUID
    bestellnummer: str
    status: str
    liefertermin: date | None
    lieferant_name: str | None


class ZeitplanBasisplanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ZeitplanBasisplanRead(BaseModel):
    id: UUID
    name: str
    erstellt_am: datetime
    erstellt_von_name: str | None
    anzahl_elemente: int


class ZeitplanStraffenRequest(BaseModel):
    phase_id: UUID | None = None
    vorschau: bool = True


class ZeitplanAenderung(BaseModel):
    element_id: UUID
    titel: str
    alt_start_am: date
    alt_ende_am: date
    neu_start_am: date
    neu_ende_am: date


class ZeitplanStraffenRead(BaseModel):
    aenderungen: list[ZeitplanAenderung]
    zeitplan: ZeitplanRead | None


class ProjektVorlageListe(BaseModel):
    id: UUID
    name: str
    beschreibung: str | None
    anzahl_elemente: int
    dauer_tage: int


class ProjektVorlageElementRead(BaseModel):
    ref: str
    typ: ZeitplanTyp
    titel: str
    phase_ref: str | None
    offset_tage: int
    dauer_tage: int
    reihenfolge: int


class ProjektVorlageAbhaengigkeitRead(BaseModel):
    vorgaenger_ref: str
    nachfolger_ref: str
    art: AbhaengigkeitArt
    versatz_tage: int


class ProjektVorlageDetail(ProjektVorlageListe):
    elemente: list[ProjektVorlageElementRead]
    abhaengigkeiten: list[ProjektVorlageAbhaengigkeitRead]


class ProjektVorlageAusProjekt(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    beschreibung: str | None = None


class ProjektVorlageUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    beschreibung: str | None = None


class ZeitplanVorlageAnwenden(BaseModel):
    vorlage_id: UUID
    start_am: date
