from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator

VorOrtRolle = Literal["mieter", "eigentuemer", "bauherr", "hausmeister", "nutzer", "sonstige"]
VorOrtHerkunft = Literal["vorgang", "auftrag", "projekt"]

_TEXTFELDER = ("name", "einheit", "telefon", "telefon2", "email", "erreichbarkeit", "hinweis")


def _getrimmt(v):
    """Leere/whitespace-only Eingaben sind "nicht gesetzt" (None), sonst getrimmter Text."""
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


class _KontaktFelder(BaseModel):
    _trimmen = field_validator(*_TEXTFELDER, mode="before", check_fields=False)(_getrimmt)


class VorOrtKontaktCreate(_KontaktFelder):
    standort_id: UUID | None = None
    name: str | None = None
    rolle: VorOrtRolle
    einheit: str | None = None
    telefon: str | None = None
    telefon2: str | None = None
    email: EmailStr | None = None
    erreichbarkeit: str | None = None
    hinweis: str | None = None

    @model_validator(mode="after")
    def _name_oder_telefon(self) -> "VorOrtKontaktCreate":
        if not self.name and not self.telefon:
            raise ValueError("Name oder Telefon angeben")
        return self


class VorOrtKontaktUpdate(_KontaktFelder):
    """Alle Felder optional (exclude_unset). Die Regel "Name oder Telefon" gilt fuer das Ergebnis und wird
    deshalb im Service gegen den bestehenden Datensatz geprueft."""

    standort_id: UUID | None = None
    name: str | None = None
    rolle: VorOrtRolle | None = None
    einheit: str | None = None
    telefon: str | None = None
    telefon2: str | None = None
    email: EmailStr | None = None
    erreichbarkeit: str | None = None
    hinweis: str | None = None

    @model_validator(mode="after")
    def _rolle_nicht_null(self) -> "VorOrtKontaktUpdate":
        if "rolle" in self.model_fields_set and self.rolle is None:
            raise ValueError("rolle darf nicht null sein")
        return self


class VorOrtKontaktOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kunde_id: UUID
    standort_id: UUID | None
    # Nicht persistiert, vom Service gesetzt.
    standort_bezeichnung: str | None = None
    name: str | None
    rolle: VorOrtRolle
    einheit: str | None
    telefon: str | None
    telefon2: str | None
    # Bewusst str statt EmailStr: Altdaten/Importe duerfen die Antwort nicht scheitern lassen.
    email: str | None
    erreichbarkeit: str | None
    hinweis: str | None
    quelle: str | None
    letzter_einsatz_am: datetime | None
    anonymisiert_am: datetime | None
    created_at: datetime
    updated_at: datetime
    # Alle Zuordnungen / nur die zu noch offenen Zielen (Vorgang nicht geschlossen, Auftrag offen/in_arbeit,
    # Projekt nicht archiviert). Nicht persistiert.
    zuordnungen_anzahl: int = 0
    offene_zuordnungen_anzahl: int = 0


class VorOrtKontaktZugeordnet(BaseModel):
    zuordnung_id: UUID
    kontakt: VorOrtKontaktOut
    ist_hauptkontakt: bool
    # Ebene, auf der die Zuordnung liegt; herkunft_titel: Vorgangsnummer, Auftragstitel bzw. Projektname.
    herkunft: VorOrtHerkunft
    herkunft_id: UUID
    herkunft_titel: str


class VorOrtZuordnungCreate(BaseModel):
    kontakt_id: UUID | None = None
    neu: VorOrtKontaktCreate | None = None
    ist_hauptkontakt: bool = False

    @model_validator(mode="after")
    def _genau_eins(self) -> "VorOrtZuordnungCreate":
        if (self.kontakt_id is None) == (self.neu is None):
            raise ValueError("Genau eines von kontakt_id oder neu angeben")
        return self


class VorOrtZuordnungUpdate(BaseModel):
    ist_hauptkontakt: bool


class VorOrtHauptkontaktKurz(BaseModel):
    name: str | None
    rolle: VorOrtRolle
    telefon: str | None
    einheit: str | None
