from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.auftrag import AuftragStatus
from app.schemas.vorgang import VorgangStatus

HerkunftArt = Literal[
    "projekt_angelegt",
    "auftrag_angelegt",
    "vorgang_angelegt",
    "folge_vorgang",
    "zuordnung_geaendert",
    "eigenstaendig_gesetzt",
    "eigenstaendig_aufgehoben",
]


class EigenstaendigBody(BaseModel):
    eigenstaendig: bool


class HerkunftSchritt(BaseModel):
    art: HerkunftArt
    text: str
    ref_typ: Literal["projekt", "auftrag", "vorgang"] | None = None
    ref_id: UUID | None = None
    ref_label: str | None = None
    datum: datetime
    person_name: str | None = None
    zusatz: str | None = None
    aktuell: bool = False


class Rueckmeldung(BaseModel):
    arbeitszeit_sekunden: int
    arbeitszeit_sekunden_auftrag: int | None
    positionen_anzahl: int
    # Derzeit immer null: die Positionen (Materialbedarf, -verwendung,
    # LV-Buchung) haben keine einheitlich bepreiste Netto-Summe.
    positionen_netto: Decimal | None
    offene_maengel: int
    status: VorgangStatus


class VerknuepfungGeschwister(BaseModel):
    id: UUID
    vorgangsnummer: str
    titel: str
    status: VorgangStatus
    ist_aktuell: bool


class VerknuepfungProjekt(BaseModel):
    id: UUID
    name: str


class VerknuepfungAuftrag(BaseModel):
    id: UUID
    titel: str
    status: AuftragStatus


class VorgangVerknuepfung(BaseModel):
    herkunft: list[HerkunftSchritt]
    rueckmeldung: Rueckmeldung
    geschwister: list[VerknuepfungGeschwister]
    projekt: VerknuepfungProjekt | None
    auftrag: VerknuepfungAuftrag | None
