from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

# Toleranz gegen Uhrzeit-Abweichungen zwischen Client und Server -- ohne
# das wuerde ein "jetzt" vom Handy knapp nach dem Server-"jetzt" faelschlich
# als Zukunft abgelehnt.
_ZUKUNFT_TOLERANZ = timedelta(minutes=2)

# Muss mit ZEITERFASSUNG_KATEGORIEN in app/models/zeiterfassung.py
# uebereinstimmen.
ZeiterfassungKategorie = Literal[
    "auftrag", "verwaltung", "fahrzeit", "schulung", "pause", "urlaub", "krankheit", "sonstiges"
]

# Muss mit ZEITERFASSUNG_BUCHUNGSSTATUS in app/models/zeiterfassung.py
# uebereinstimmen (docs/konzepte/ZEITERFASSUNG.md, Abschnitt 6.1).
ZeiterfassungBuchungsstatus = Literal["vermerkt", "vorgemerkt", "gebucht", "abgerechnet"]

# Kategorien, die nicht als geleistete Arbeitszeit zaehlen (siehe
# get_statistik in app/api/routes/zeiterfassung.py) -- Pause/Urlaub/
# Krankheit sind Abwesenheit von der eigentlichen Arbeit.
ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT = ("pause", "urlaub", "krankheit")

# Fuer PDF/CSV-Export (app/services/pdf_service.py, app/api/routes/
# zeiterfassung.py) -- "auftrag" hat bewusst kein Label, dort steht die
# Vorgangsnummer statt einer Kategorie-Bezeichnung.
ZEITERFASSUNG_KATEGORIE_LABEL: dict[str, str] = {
    "verwaltung": "Verwaltung",
    "fahrzeit": "Fahrzeit",
    "schulung": "Schulung",
    "pause": "Pause",
    "urlaub": "Urlaub",
    "krankheit": "Krankheit",
    "sonstiges": "Sonstiges",
}

# Fuer CSV-Export (app/api/routes/zeiterfassung.py) -- muss mit
# BUCHUNGSSTATUS_LABEL in frontend/src/utils/zeiterfassung.ts uebereinstimmen.
ZEITERFASSUNG_BUCHUNGSSTATUS_LABEL: dict[str, str] = {
    "vermerkt": "Vermerkt",
    "vorgemerkt": "Vorgemerkt",
    "gebucht": "Gebucht",
    "abgerechnet": "Abgerechnet",
}


class ZeiterfassungStatistik(BaseModel):
    wochenstunden: Decimal
    monatsstunden: Decimal
    jahresstunden: Decimal


class ZeiterfassungStatusSumme(BaseModel):
    arbeitszeit_stunden: Decimal
    fahrzeit_stunden: Decimal
    km: Decimal


# Fuer den "Zeit"-Block im Auftrag-/Projekt-Panel (Stufe 4, docs/konzepte/
# ZEITERFASSUNG.md Abschnitt 7.4) -- Summen ueber alle Vorgaenge eines
# Auftrags/Projekts, je Buchungsstatus.
class ZeiterfassungSummenNachStatus(BaseModel):
    vermerkt: ZeiterfassungStatusSumme
    vorgemerkt: ZeiterfassungStatusSumme
    gebucht: ZeiterfassungStatusSumme
    abgerechnet: ZeiterfassungStatusSumme


class ZeiterfassungStart(BaseModel):
    vorgang_id: UUID
    taetigkeit: str | None = None
    abrechenbar: bool = True


class ZeiterfassungManuellCreate(BaseModel):
    start_at: datetime
    ende_at: datetime
    kategorie: ZeiterfassungKategorie
    vorgang_id: UUID | None = None
    taetigkeit: str | None = None
    abrechenbar: bool = False
    # Stundenverrechnungssatz aus dem Leistungsverzeichnis des Kunden --
    # nur sinnvoll bei kategorie="auftrag" (Praefung erfolgt in der Route,
    # nicht hier, analog zur vorgang_id-Pflichtpruefung).
    lv_position_id: UUID | None = None
    # Nur mit dem Recht "Zeiten buchen" erlaubt (Konzept 6.2, "fuer einen
    # anderen nachtragen") -- ohne das Recht lehnt die Route ein abweichendes
    # techniker_id ab, statt es stillschweigend zu ignorieren.
    techniker_id: UUID | None = None
    # Fahrten mit km (Stufe 3) -- nur bei kategorie="fahrzeit" erlaubt,
    # Pruefung in der Route (siehe app/models/zeiterfassung.py).
    km: Decimal | None = None
    fahrzeug_id: UUID | None = None

    @model_validator(mode="after")
    def _ende_nach_start(self) -> "ZeiterfassungManuellCreate":
        if self.ende_at <= self.start_at:
            raise ValueError("Ende muss nach dem Start liegen")
        # Nur der Start wird geprueft: ein bereits begonnener Eintrag (z.B.
        # "Urlaub ab jetzt, ganzer Tag") endet legitim erst spaeter am selben
        # Tag -- das Ende darf also in der (nahen) Zukunft liegen.
        grenze = datetime.now(UTC) + _ZUKUNFT_TOLERANZ
        if self.start_at > grenze:
            raise ValueError("Start darf nicht in der Zukunft liegen")
        return self


class ZeiterfassungUpdate(BaseModel):
    start_at: datetime | None = None
    ende_at: datetime | None = None
    kategorie: ZeiterfassungKategorie | None = None
    vorgang_id: UUID | None = None
    taetigkeit: str | None = None
    abrechenbar: bool | None = None
    lv_position_id: UUID | None = None
    km: Decimal | None = None
    fahrzeug_id: UUID | None = None
    # Pflicht, wenn Buchungsberechtigte einen fremden Eintrag aendern
    # (Konzept 6.2) -- landet im Protokoll, wird selbst nicht gespeichert.
    grund: str | None = None


class ZeiterfassungRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vorgang_id: UUID | None
    # Transient, nicht in der DB -- wird von den Routen per setattr() auf
    # die ORM-Instanz gesetzt, siehe _mit_vorgangsnummer in
    # app/api/routes/zeiterfassung.py. None, wenn kein Vorgang verknuepft ist.
    vorgangsnummer: str | None = None
    # Transient wie vorgangsnummer -- fuer die Seite "Zeiten buchen"
    # (Gruppierung/Filter nach Kunde/Auftrag/Projekt, siehe _mit_vorgang_kontext
    # in app/api/routes/zeiterfassung.py). None, wenn kein Vorgang verknuepft ist.
    vorgang_kunde_id: UUID | None = None
    vorgang_auftrag_id: UUID | None = None
    vorgang_projekt_id: UUID | None = None
    techniker_id: UUID
    start_at: datetime
    ende_at: datetime | None
    taetigkeit: str | None
    abrechenbar: bool
    kategorie: ZeiterfassungKategorie
    lv_position_id: UUID | None
    buchungsstatus: ZeiterfassungBuchungsstatus
    vorgemerkt_von: UUID | None
    vorgemerkt_am: datetime | None
    gebucht_von: UUID | None
    gebucht_am: datetime | None
    km: Decimal | None
    fahrzeug_id: UUID | None
    quelle: Literal["timer", "manuell"]
    abgerechnet_rechnung_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ZeiterfassungIdsBody(BaseModel):
    """Gemeinsamer Body fuer die gesammelten Buchungs-Endpunkte (vormerken/
    zurueckziehen/buchen) -- alles oder nichts, siehe Konzept 6.1."""

    ids: list[UUID]


class ZeiterfassungBuchungStornierenBody(BaseModel):
    ids: list[UUID]
    # Pflicht (Konzept 6.1: "gebucht -> vermerkt: Grund Pflicht").
    grund: str


class ZeiterfassungStopBody(BaseModel):
    """Body fuer POST /{id}/stop -- alle Felder optional und nur wirksam,
    wenn ein Buchungsberechtigter den Timer eines ANDEREN beendet (Konzept
    7.1/6.2: "Ende frei waehlbar", Grund Pflicht). Beim eigenen Timer werden
    beide Felder ignoriert (Ende ist immer "jetzt")."""

    ende_at: datetime | None = None
    grund: str | None = None


class ZeiterfassungAenderungRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    aktion: str
    feld: str | None
    alter_wert: object | None
    neuer_wert: object | None
    grund: str | None
    geaendert_von: UUID | None
    geaendert_am: datetime
