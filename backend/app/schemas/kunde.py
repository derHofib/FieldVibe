from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.kontakt import AnsprechpartnerEintrag
from app.services import leitweg_id
from app.schemas.personenkonto import personenkonto_normalisieren

KundeTyp = Literal["privat", "gewerbe", "oeffentlich", "hausverwaltung"]
# Automatik (NULL) ist kein Wert dieses Literals, sondern None am Feld.
KundeEmpfangsformat = Literal["zugferd", "xrechnung"]


def _leitweg_id_pruefen(wert: str | None) -> str | None:
    return leitweg_id.normalisiere_und_pruefe(wert)


class KundeCreate(BaseModel):
    kundennummer: str | None = None
    name: str
    typ: KundeTyp | None = None
    ansprechpartner: list[AnsprechpartnerEintrag] = Field(default_factory=list)
    adresse: dict | None = None
    notiz: str | None = None
    ust_idnr: str | None = None
    ust_13b_nachweis_bis: date | None = None
    leitweg_id: str | None = None
    e_rechnung_format: KundeEmpfangsformat | None = None

    _leitweg_pruefen = field_validator("leitweg_id")(_leitweg_id_pruefen)
    debitorenkonto: str | None = None

    @field_validator("debitorenkonto")
    @classmethod
    def _debitorenkonto_pruefen(cls, v: str | None) -> str | None:
        return personenkonto_normalisieren(v, "Debitorenkonto")


class KundeLogoUrl(BaseModel):
    url: str | None


class KundeUpdate(BaseModel):
    name: str | None = None
    typ: KundeTyp | None = None
    ansprechpartner: list[AnsprechpartnerEintrag] | None = None
    adresse: dict | None = None
    notiz: str | None = None
    ust_idnr: str | None = None
    ust_13b_nachweis_bis: date | None = None
    leitweg_id: str | None = None
    e_rechnung_format: KundeEmpfangsformat | None = None

    _leitweg_pruefen = field_validator("leitweg_id")(_leitweg_id_pruefen)
    debitorenkonto: str | None = None

    @field_validator("debitorenkonto")
    @classmethod
    def _debitorenkonto_pruefen(cls, v: str | None) -> str | None:
        return personenkonto_normalisieren(v, "Debitorenkonto")


class KundeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kundennummer: str
    name: str
    typ: KundeTyp | None
    ansprechpartner: list[AnsprechpartnerEintrag]
    adresse: dict | None
    notiz: str | None
    ust_idnr: str | None
    ust_13b_nachweis_bis: date | None
    leitweg_id: str | None = None
    e_rechnung_format: KundeEmpfangsformat | None = None
    debitorenkonto: str | None
    portal_slug: str
    logo_object_key: str | None
    created_at: datetime
    updated_at: datetime
