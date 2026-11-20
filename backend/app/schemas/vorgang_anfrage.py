from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.vor_ort_kontakt import VorOrtRolle, _getrimmt
from app.schemas.vorgang import Leistungstyp, VorgangAbrechnungsart

VorgangAnfrageStatus = Literal["offen", "angenommen", "abgelehnt"]


MAX_ANFRAGE_KONTAKTE = 5


class VorgangAnfrageKontakt(BaseModel):
    """Kontakt vor Ort, den das Portal mitgibt. Bewusst ohne E-Mail (Datensparsamkeit); bis zur Annahme als
    JSONB an der Anfrage, danach als vor_ort_kontakte-Zeile."""

    name: str | None = None
    rolle: VorOrtRolle
    telefon: str | None = None
    erreichbarkeit: str | None = Field(default=None, max_length=200)
    hinweis: str | None = Field(default=None, max_length=500)

    _trimmen = field_validator("name", "telefon", "erreichbarkeit", "hinweis", mode="before")(_getrimmt)

    @model_validator(mode="after")
    def _name_oder_telefon(self) -> "VorgangAnfrageKontakt":
        if not self.name and not self.telefon:
            raise ValueError("Name oder Telefon angeben")
        return self


class VorgangAnfrageCreate(BaseModel):
    titel: str
    beschreibung: str | None = None
    leistungstyp: Leistungstyp
    standort_id: UUID | None = None
    anlage_id: UUID | None = None
    einheit: str | None = Field(default=None, max_length=200)
    kunden_referenz: str | None = Field(default=None, max_length=200)
    vor_ort_kontakte: list[VorgangAnfrageKontakt] = Field(default_factory=list, max_length=MAX_ANFRAGE_KONTAKTE)

    _trimmen = field_validator("einheit", "kunden_referenz", mode="before")(_getrimmt)


class VorgangAnfrageAnnehmen(BaseModel):
    abrechnungsart: VorgangAbrechnungsart
    prioritaet: int = Field(default=3, ge=1, le=5)


class VorgangAnfrageAblehnen(BaseModel):
    ablehnungsgrund: str | None = None


class VorgangAnfrageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kunde_id: UUID
    kundenportal_zugang_id: UUID
    standort_id: UUID | None
    anlage_id: UUID | None
    titel: str
    beschreibung: str | None
    leistungstyp: Leistungstyp
    einheit: str | None = None
    kunden_referenz: str | None = None
    # Nur bis zur Annahme/Ablehnung gefuellt; danach liegen die Daten in vor_ort_kontakte (bzw. sind geloescht).
    vor_ort_kontakte: list[VorgangAnfrageKontakt] = Field(default_factory=list)
    status: VorgangAnfrageStatus
    ablehnungsgrund: str | None
    vorgang_id: UUID | None
    bearbeitet_von: UUID | None
    bearbeitet_am: datetime | None
    created_at: datetime
    updated_at: datetime

    # Rein lesend, vom Join in der Route befuellt (nicht schreibbar).
    kunde_name: str | None = None
    standort_bezeichnung: str | None = None
    anlage_bezeichnung: str | None = None
    gestellt_von_name: str | None = None
    gestellt_von_email: str | None = None
    vorgang_nummer: str | None = None
    bearbeitet_von_name: str | None = None
