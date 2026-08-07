from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

# Muss mit ZEITERFASSUNG_KATEGORIEN in app/models/zeiterfassung.py
# uebereinstimmen.
ZeiterfassungKategorie = Literal[
    "auftrag", "verwaltung", "fahrzeit", "schulung", "pause", "urlaub", "krankheit", "sonstiges"
]

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


class ZeiterfassungStatistik(BaseModel):
    wochenstunden: Decimal
    monatsstunden: Decimal
    jahresstunden: Decimal


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

    @model_validator(mode="after")
    def _ende_nach_start(self) -> "ZeiterfassungManuellCreate":
        if self.ende_at <= self.start_at:
            raise ValueError("Ende muss nach dem Start liegen")
        return self


class ZeiterfassungUpdate(BaseModel):
    start_at: datetime | None = None
    ende_at: datetime | None = None
    kategorie: ZeiterfassungKategorie | None = None
    vorgang_id: UUID | None = None
    taetigkeit: str | None = None
    abrechenbar: bool | None = None


class ZeiterfassungRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vorgang_id: UUID | None
    # Transient, nicht in der DB -- wird von den Routen per setattr() auf
    # die ORM-Instanz gesetzt, siehe _mit_vorgangsnummer in
    # app/api/routes/zeiterfassung.py. None, wenn kein Vorgang verknuepft ist.
    vorgangsnummer: str | None = None
    techniker_id: UUID
    start_at: datetime
    ende_at: datetime | None
    taetigkeit: str | None
    abrechenbar: bool
    kategorie: ZeiterfassungKategorie
    created_at: datetime
    updated_at: datetime
