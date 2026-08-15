from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

PartnerNachweisTyp = Literal[
    "freistellungsbescheinigung",
    "haftpflichtversicherung",
    "gewerbeanmeldung",
    "handwerksrolle",
    "avv_dsgvo",
    "sonstiges",
]
PartnerFreigabeStatus = Literal["vorgeschlagen", "angenommen", "abgelehnt"]


class PartnerCreate(BaseModel):
    name: str
    gewerk: str | None = None
    ansprechpartner: str | None = None
    telefon: str | None = None
    email: str | None = None
    adresse: dict | None = None
    notiz: str | None = None


class PartnerUpdate(BaseModel):
    name: str | None = None
    gewerk: str | None = None
    ansprechpartner: str | None = None
    telefon: str | None = None
    email: str | None = None
    adresse: dict | None = None
    notiz: str | None = None
    aktiv: bool | None = None


class PartnerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    gewerk: str | None
    ansprechpartner: str | None
    telefon: str | None
    email: str | None
    adresse: dict | None
    notiz: str | None
    aktiv: bool
    created_at: datetime
    updated_at: datetime


class PartnerNachweisCreate(BaseModel):
    typ: PartnerNachweisTyp
    gueltig_bis: date | None = None
    dokument_s3_key: str | None = None
    notiz: str | None = None


class PartnerNachweisUpdate(BaseModel):
    gueltig_bis: date | None = None
    dokument_s3_key: str | None = None
    notiz: str | None = None


class PartnerNachweisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    partner_id: UUID
    typ: PartnerNachweisTyp
    gueltig_bis: date | None
    dokument_s3_key: str | None
    notiz: str | None
    abgelaufen: bool
    created_at: datetime
    updated_at: datetime


class PartnerZugangCreate(BaseModel):
    email: EmailStr
    password: str
    name: str

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class PartnerZugangUpdate(BaseModel):
    name: str | None = None
    aktiv: bool | None = None
    # Fallback ohne konfiguriertes SMTP, analog KundenportalZugangUpdate.
    password: str | None = None


class PartnerZugangRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    partner_id: UUID
    email: str
    name: str
    aktiv: bool
    created_at: datetime
    updated_at: datetime


class VorgangPartnerZuweisung(BaseModel):
    # partner_id=None hebt eine bestehende Delegation wieder auf (setzt auch
    # freigabe_status/ablehnung_grund/honorar zurueck).
    partner_id: UUID | None
    partner_honorar_netto: Decimal | None = None


class PartnerAntwort(BaseModel):
    status: Literal["angenommen", "abgelehnt"]
    ablehnung_grund: str | None = None


class CurrentPartner(BaseModel):
    zugang_id: UUID
    partner_id: UUID
    partner_name: str
    name: str
    email: str


class PartnerPasswortVergessenRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class PartnerPasswortResetRequest(BaseModel):
    token: str
    new_password: str


class PartnerVorgangKommentar(BaseModel):
    body: str


class PartnerVorgangStatusUpdate(BaseModel):
    status: Literal["in_arbeit", "wartet_kunde", "abgeschlossen"]


class PartnerVorgangRead(BaseModel):
    """Bewusst reduzierte Sicht auf einen delegierten Vorgang: der Partner
    sieht den technischen Umfang und die Einsatzadresse, aber weder
    Kundennummer/Vertragskonditionen noch den Angebots-/Rechnungsbetrag,
    den der Endkunde zahlt (Datenminimierung nach Art. 5 Abs. 1c DSGVO,
    und schlicht keine Information, die fuer die Ausfuehrung noetig ist)."""

    id: UUID
    vorgangsnummer: str
    titel: str
    beschreibung: str | None
    leistungstyp: str
    status: str
    partner_freigabe_status: PartnerFreigabeStatus | None
    partner_ablehnung_grund: str | None
    partner_honorar_netto: Decimal | None
    kunde_name: str
    anlage_bezeichnung: str | None
    anlage_adresse: dict | None
    last_activity_at: datetime
    created_at: datetime


class VorgangPartnerZuweisungResponse(BaseModel):
    """`freistellungsbescheinigung_warnung=True` heisst: fuer diesen Partner
    liegt keine gueltige Freistellungsbescheinigung vor -- die Zuweisung
    wird trotzdem durchgefuehrt (das ist eine kaufmaennische Entscheidung,
    kein technischer Blocker), aber bei Zahlungen fuer Bauleistungen greift
    ohne sie grundsaetzlich die 15%-Bauabzugsteuer nach § 48 EStG."""

    vorgang_id: UUID
    partner_id: UUID | None
    partner_freigabe_status: PartnerFreigabeStatus | None
    freistellungsbescheinigung_warnung: bool
