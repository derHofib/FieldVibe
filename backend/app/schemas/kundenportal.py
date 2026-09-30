from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.vorgang import Leistungstyp, VorgangStatus
from app.schemas.vorgang_event import EventType


class KundenportalLinkInfo(BaseModel):
    """Oeffentliche Antwort fuer den personalisierten Login-Link (kein Auth
    noetig, keine sensiblen Daten): ein Link pro Kunde, den jeder
    Mitarbeiter dieses Kunden nutzen kann -- zeigt nur Name/Logo des Kunden
    zur Wiedererkennung, das Passwort bleibt in jedem Fall Pflicht und ist
    weiterhin an den jeweils eigenen KundenportalZugang gebunden."""

    kunde_name: str
    mandant_name: str
    hat_logo: bool


class CurrentKunde(BaseModel):
    zugang_id: UUID
    kunde_id: UUID
    kunde_name: str
    name: str
    email: str


class KundenportalZugangUpdate(BaseModel):
    name: str | None = None
    aktiv: bool | None = None
    # Fallback ohne konfiguriertes SMTP (siehe app/services/email_service.py):
    # ein Mitarbeiter kann das Passwort direkt neu setzen, statt den Zugang
    # deaktivieren und neu anlegen zu muessen.
    password: str | None = None


class KundenAngebotAntwort(BaseModel):
    status: str


class KundenPasswortVergessenRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class KundenPasswortResetRequest(BaseModel):
    token: str
    new_password: str


class KundenportalZugangRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kunde_id: UUID
    email: str
    name: str
    aktiv: bool
    created_at: datetime
    updated_at: datetime


class KundenStandortCreate(BaseModel):
    bezeichnung: str
    adresse: dict = Field(default_factory=dict)
    geo_lat: float | None = None
    geo_lng: float | None = None


class KundenAnlageCreate(BaseModel):
    standort_id: UUID | None = None
    bezeichnung: str
    adresse: dict = Field(default_factory=dict)
    anlagentyp: str | None = None
    geo_lat: float | None = None
    geo_lng: float | None = None


class VorgangPortalRead(BaseModel):
    """Whitelist fuer den Endkunden: bewusst ohne Honorar-/Partner-Felder,
    Abrechnungsart, Prioritaet, Wiedervorlage und interne Nutzer-IDs
    (Datenminimierung, Einkaufspreise des Betriebs sind Geschaeftsgeheimnis).
    Neue Vorgang-Felder erscheinen hier nie automatisch."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vorgangsnummer: str
    titel: str
    beschreibung: str | None
    leistungstyp: Leistungstyp
    status: VorgangStatus
    faelligkeit_am: datetime | None
    anlage_id: UUID | None
    standort_id: UUID | None
    abgeschlossen_am: datetime | None
    last_activity_at: datetime
    created_at: datetime
    updated_at: datetime


# Nur Ereignistypen, die fuer den Kunden eine Bedeutung haben -- zusaetzlich
# zum kundensichtbar-Flag, damit ein versehentlich freigegebenes
# Zeit-/Material-/Eingangsrechnungs-Event nie beim Kunden landet.
PORTAL_EVENT_TYPEN: tuple[str, ...] = (
    "kommentar",
    "status_change",
    "foto",
    "dokument",
    "angebot",
    "termin",
    "unterschrift",
    "formular",
    "leistung",
    "system",
)


class VorgangEventPortalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vorgang_id: UUID
    event_type: EventType
    is_system: bool
    body: str | None
    created_at: datetime
    foto_url: str | None = None
    foto_thumbnail_url: str | None = None
    unterschrift_url: str | None = None
    dokument_url: str | None = None
    dokument_dateiname: str | None = None
