from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.kontakt import AnsprechpartnerEintrag
from app.schemas.kunde_kurz import RechnungAnKurz

AuftragStatus = Literal["offen", "in_arbeit", "abgeschlossen", "storniert"]


def _text_oder_none(v: str | None) -> str | None:
    if v is None:
        return v
    return v.strip() or None


class AuftragCreate(BaseModel):
    projekt_id: UUID | None = None
    kunde_id: UUID | None = None
    # Leistungsort: Standort muss zum Kunden gehoeren, ansprechpartner_id in kunden.ansprechpartner stehen.
    standort_id: UUID | None = None
    einheit: str | None = None
    ansprechpartner_id: UUID | None = None
    kunden_referenz: str | None = None
    # Abweichender Rechnungsempfaenger (z. B. WEG); None = Auftraggeber.
    rechnung_an_kunde_id: UUID | None = None
    titel: str
    beschreibung: str | None = None

    _trimmen = field_validator("einheit", "kunden_referenz")(_text_oder_none)

    @field_validator("titel")
    @classmethod
    def _titel_nicht_leer(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Titel darf nicht leer sein")
        return v


class AuftragUpdate(BaseModel):
    projekt_id: UUID | None = None
    kunde_id: UUID | None = None
    standort_id: UUID | None = None
    einheit: str | None = None
    ansprechpartner_id: UUID | None = None
    kunden_referenz: str | None = None
    rechnung_an_kunde_id: UUID | None = None
    titel: str | None = None
    beschreibung: str | None = None
    status: AuftragStatus | None = None

    _trimmen = field_validator("einheit", "kunden_referenz")(_text_oder_none)

    @field_validator("titel")
    @classmethod
    def _titel_nicht_leer(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Titel darf nicht leer sein")
        return v


class AuftragStandortKurz(BaseModel):
    id: UUID
    bezeichnung: str
    adresse: dict


class AuftragRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    # Herkunft: "ki" bei Anlage per KI-Assistent (MCP), sonst "app" (Migration 0129).
    erstellt_via: Literal["app", "ki"] = "app"
    projekt_id: UUID | None
    kunde_id: UUID | None
    standort_id: UUID | None
    einheit: str | None
    ansprechpartner_id: UUID | None
    kunden_referenz: str | None
    rechnung_an_kunde_id: UUID | None = None
    titel: str
    beschreibung: str | None
    status: AuftragStatus
    erstellt_von: UUID
    created_at: datetime
    updated_at: datetime
    # Nicht persistiert, sondern in den Routen transient gesetzt (gleiches
    # Muster wie VorgangRead.zugewiesener_name) -- erspart dem Frontend
    # zusaetzliche Kunde/Vorgang-Anzahl-Abfragen fuer die Tabellen-Ansicht.
    kunde_name: str | None = None
    vorgaenge_gesamt: int = 0
    projekt_name: str | None = None
    # Geschlossene Vorgaenge (abgeschlossen/abgerechnet/storniert, also
    # VORGANG_STATUS_GESCHLOSSEN). Bewusst inklusive storniert, weil
    # vorgaenge_gesamt stornierte mitzaehlt -- sonst erreichte ein Auftrag mit
    # einem stornierten Vorgang nie "alle erledigt".
    vorgaenge_erledigt: int = 0
    # Aufgeloest aus standort_id bzw. kunden.ansprechpartner; nicht gefunden (z. B. Ansprechpartner
    # inzwischen entfernt) -> None.
    standort: AuftragStandortKurz | None = None
    ansprechpartner: AnsprechpartnerEintrag | None = None
    rechnung_an: RechnungAnKurz | None = None
