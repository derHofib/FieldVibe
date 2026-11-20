from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TelefonatRichtung = Literal["ausgehend", "eingehend"]
TelefonatErgebnis = Literal["erreicht", "nicht_erreicht", "mailbox"]
TelefonatErstelltVia = Literal["app", "claude"]


def _mit_zeitzone(wert: datetime | None) -> datetime | None:
    # Naive Zeitstempel aus Offline-Outbox/Skripten gelten als UTC; asyncpg lehnt sie fuer timestamptz sonst ab.
    if wert is not None and wert.tzinfo is None:
        return wert.replace(tzinfo=UTC)
    return wert


class TelefonatCreate(BaseModel):
    vorgang_id: UUID | None = None
    kunde_id: UUID | None = None
    ansprechpartner_id: UUID | None = None
    # Kontakt vor Ort (Mieter, Hausmeister ...) statt Ansprechpartner; muss zum Kunden des Telefonats gehoeren.
    vor_ort_kontakt_id: UUID | None = None
    partner_name: str = Field(min_length=1, max_length=200)
    partner_nummer: str | None = Field(default=None, max_length=50)
    richtung: TelefonatRichtung
    ergebnis: TelefonatErgebnis
    beginn: datetime
    dauer_sekunden: int | None = Field(default=None, ge=0, le=86400)
    notiz: str | None = Field(default=None, max_length=10000)
    rueckruf_am: datetime | None = None
    als_arbeitszeit_buchen: bool = False
    client_uuid: UUID | None = None

    _tz = field_validator("beginn", "rueckruf_am")(_mit_zeitzone)

    @field_validator("partner_name")
    @classmethod
    def _name_nicht_leer(cls, wert: str) -> str:
        wert = wert.strip()
        if not wert:
            raise ValueError("Der Gesprächspartner darf nicht leer sein")
        return wert

    @model_validator(mode="after")
    def _regeln(self) -> "TelefonatCreate":
        if self.vorgang_id is None and self.kunde_id is None:
            raise ValueError("Ein Telefonat braucht einen Vorgang oder einen Kunden")
        if self.ansprechpartner_id is not None and self.vor_ort_kontakt_id is not None:
            raise ValueError("Entweder Ansprechpartner oder Kontakt vor Ort angeben")
        if self.ergebnis == "erreicht" and not (self.notiz or "").strip():
            raise ValueError("Bei einem erreichten Gespräch ist eine Notiz Pflicht")
        if self.als_arbeitszeit_buchen:
            if self.vorgang_id is None:
                raise ValueError("Arbeitszeit lässt sich nur für ein Telefonat an einem Vorgang buchen")
            if self.ergebnis != "erreicht":
                raise ValueError("Arbeitszeit lässt sich nur für ein erreichtes Gespräch buchen")
            if not self.dauer_sekunden:
                raise ValueError("Zum Buchen der Arbeitszeit ist eine Dauer größer 0 nötig")
        return self


class TelefonatUpdate(BaseModel):
    partner_name: str | None = Field(default=None, min_length=1, max_length=200)
    partner_nummer: str | None = Field(default=None, max_length=50)
    ansprechpartner_id: UUID | None = None
    vor_ort_kontakt_id: UUID | None = None
    richtung: TelefonatRichtung | None = None
    ergebnis: TelefonatErgebnis | None = None
    beginn: datetime | None = None
    dauer_sekunden: int | None = Field(default=None, ge=0, le=86400)
    notiz: str | None = Field(default=None, max_length=10000)
    rueckruf_am: datetime | None = None
    rueckruf_erledigt: bool | None = None

    _tz = field_validator("beginn", "rueckruf_am")(_mit_zeitzone)

    @model_validator(mode="after")
    def _pflichtfelder_nicht_nullen(self) -> "TelefonatUpdate":
        # Ein explizites null auf Pflichtfeldern waere ein stilles "unveraendert" -- lieber ablehnen.
        for feld in ("partner_name", "richtung", "ergebnis", "beginn"):
            if feld in self.model_fields_set and getattr(self, feld) is None:
                raise ValueError(f"{feld} darf nicht leer sein")
        return self


class TelefonatVorOrtKontakt(BaseModel):
    id: UUID
    name: str | None
    rolle: str


class NummerOffenerVorgang(BaseModel):
    id: UUID
    vorgangsnummer: str
    titel: str


class NummerZuordnung(BaseModel):
    """Treffer der Rufnummer-Erkennung (ziffernnormalisiert, nur nicht anonymisierte Kontakte)."""

    kunde_id: UUID
    kunde_name: str
    ansprechpartner_id: UUID | None = None
    vor_ort_kontakt_id: UUID | None = None
    # Name des erkannten Ansprechpartners bzw. Kontakts (fuer partner_name im Formular).
    partner_name: str | None = None
    offene_vorgaenge: list[NummerOffenerVorgang] = Field(default_factory=list)


class TelefonatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kunde_id: UUID | None
    kunde_name: str | None = None
    vorgang_id: UUID | None
    vorgang_nummer: str | None = None
    vorgang_titel: str | None = None
    ansprechpartner_id: UUID | None
    vor_ort_kontakt_id: UUID | None = None
    # Nicht persistiert: Name ist None, wenn der Kontakt anonymisiert wurde.
    vor_ort_kontakt: TelefonatVorOrtKontakt | None = None
    partner_name: str
    partner_nummer: str | None
    richtung: TelefonatRichtung
    ergebnis: TelefonatErgebnis
    erstellt_via: TelefonatErstelltVia
    beginn: datetime
    dauer_sekunden: int | None
    notiz: str | None
    rueckruf_am: datetime | None
    rueckruf_erledigt_am: datetime | None
    zeiterfassung_id: UUID | None
    erfasst_von: UUID
    erfasst_von_name: str | None = None
    created_at: datetime
    updated_at: datetime


class TelefonatAnzahlRueckrufe(BaseModel):
    anzahl: int


class KontaktverlaufEmail(BaseModel):
    id: UUID
    betreff: str
    empfaenger: str
    status: str
    vorgang_id: UUID | None
    vorgang_nummer: str | None
    # email_log kennt keinen eigenen Versandzeitpunkt: created_at ist der Zeitpunkt des Versands bzw.
    # des Einstellens in die Outbox; gesendet_am nur bei Status "gesendet".
    gesendet_am: datetime | None
    created_at: datetime


class KontaktverlaufEintrag(BaseModel):
    art: Literal["telefonat", "email"]
    zeit: datetime
    telefonat: TelefonatRead | None = None
    email: KontaktverlaufEmail | None = None
