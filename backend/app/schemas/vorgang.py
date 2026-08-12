from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

VorgangAbrechnungsart = Literal[
    "pauschale", "aufwand", "festpreis", "wartungsvertrag", "gewaehrleistung"
]
Leistungstyp = Literal["installation", "pruefung", "wartung", "stoerung", "beratung", "planung"]
VorgangStatus = Literal[
    "neu", "geplant", "in_arbeit", "wartet_kunde", "abgeschlossen", "abgerechnet", "storniert"
]
# "abgerechnet" bewusst ausgenommen: dieser Status wird ausschliesslich vom
# Rechnungs-Workflow gesetzt (app/api/routes/rechnungen.py, beim Bezahlen
# einer verknuepften Rechnung), nicht per direktem PATCH auf den Vorgang --
# sonst liesse sich ein Vorgang als abgerechnet markieren, ohne dass je eine
# bezahlte Rechnung dafuer existiert.
VorgangStatusSetzbar = Literal[
    "neu", "geplant", "in_arbeit", "wartet_kunde", "abgeschlossen", "storniert"
]


class VorgangCreate(BaseModel):
    vorgangsnummer: str | None = None
    kunde_id: UUID
    anlage_id: UUID | None = None
    # Weitere Anlagen zusaetzlich zur einzelnen anlage_id (der "Haupt-
    # Anlage") -- v.a. wenn beim Standort mehrere Anlagen automatisch mit
    # in den Vorgang uebernommen werden (siehe app/models/vorgang_anlage.py).
    weitere_anlage_ids: list[UUID] = Field(default_factory=list)
    standort_id: UUID | None = None
    vertrag_id: UUID | None = None
    parent_vorgang_id: UUID | None = None
    titel: str
    beschreibung: str | None = None
    abrechnungsart: VorgangAbrechnungsart
    leistungstyp: Leistungstyp
    prioritaet: int = Field(default=3, ge=1, le=5)
    faelligkeit_am: datetime | None = None
    # Optionale Adresse direkt am Vorgang, falls kein Standort angelegt
    # werden soll (z.B. einmaliger Auftrag).
    adresse: dict | None = None
    # Von der Offline-Outbox vergeben (Nacharbeit): macht einen Sync-Retry
    # sicher idempotent, dasselbe Muster wie VorgangEventCreate.client_uuid.
    client_uuid: UUID | None = None


class VorgangAnlagenHinzufuegen(BaseModel):
    anlage_ids: list[UUID]


class VorgangFolgeAuftragErstellen(BaseModel):
    leistungstyp: Leistungstyp


class VorgangUpdate(BaseModel):
    titel: str | None = None
    beschreibung: str | None = None
    kunde_id: UUID | None = None
    anlage_id: UUID | None = None
    standort_id: UUID | None = None
    vertrag_id: UUID | None = None
    abrechnungsart: VorgangAbrechnungsart | None = None
    leistungstyp: Leistungstyp | None = None
    status: VorgangStatusSetzbar | None = None
    prioritaet: int | None = Field(default=None, ge=1, le=5)
    faelligkeit_am: datetime | None = None
    adresse: dict | None = None
    # Manuelle (Neu-)Zuweisung durch mandant_admin/Dispo -- unabhaengig vom
    # Selbst-Uebernehmen-Endpoint (siehe app/api/routes/vorgaenge.py:
    # uebernehmen). Explizit auf null setzbar, um die Zuweisung aufzuheben.
    zugewiesener_user_id: UUID | None = None
    # Nur zusammen mit status="wartet_kunde" gueltig: ueberschreibt die
    # Wiedervorlage-Frist (Tage ab jetzt) fuer diesen einen Vorgang. Fehlt
    # es, greift der Mandanten- bzw. globale Default (siehe
    # app/api/routes/vorgaenge.py und Mandant.wiedervorlage_standard_tage).
    wiedervorlage_tage: int | None = Field(default=None, gt=0)


class VorgangRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vorgangsnummer: str
    kunde_id: UUID
    anlage_id: UUID | None
    standort_id: UUID | None
    vertrag_id: UUID | None
    parent_vorgang_id: UUID | None
    dauerauftrag_id: UUID | None
    titel: str
    beschreibung: str | None
    abrechnungsart: VorgangAbrechnungsart
    leistungstyp: Leistungstyp
    status: VorgangStatus
    prioritaet: int
    faelligkeit_am: datetime | None
    adresse: dict | None
    zugewiesener_user_id: UUID | None
    # Nicht persistiert, sondern in get_vorgang/update_vorgang/uebernehmen
    # transient auf dem ORM-Objekt gesetzt -- erspart dem Frontend einen
    # zusaetzlichen User-Fetch nur fuer den Namen.
    zugewiesener_name: str | None = None
    last_activity_at: datetime
    abgeschlossen_am: datetime | None
    erstellt_von_kundenportal_zugang_id: UUID | None
    erstellt_von: UUID | None
    wiedervorlage_am: datetime | None
    created_at: datetime
    updated_at: datetime
