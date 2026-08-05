from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

AnlagenObjekttyp = Literal["kundenanlage", "fahrzeug", "lager", "baustelle"]


class AnlageCreate(BaseModel):
    kunde_id: UUID | None = None
    standort_id: UUID | None = None
    objekttyp: AnlagenObjekttyp = "kundenanlage"
    bezeichnung: str
    adresse: dict = Field(default_factory=dict)
    anlagentyp: str | None = None
    qr_code: str | None = None
    hersteller: str | None = None
    modell: str | None = None
    seriennummer: str | None = None
    anschaffungsdatum: date | None = None
    notiz: str | None = None
    stammdaten: dict = Field(default_factory=dict)
    geo_lat: float | None = None
    geo_lng: float | None = None

    @model_validator(mode="after")
    def _kunde_id_passend_zu_objekttyp(self) -> "AnlageCreate":
        if self.objekttyp == "kundenanlage" and self.kunde_id is None:
            raise ValueError("kunde_id ist für objekttyp=kundenanlage erforderlich")
        if self.objekttyp != "kundenanlage" and self.kunde_id is not None:
            raise ValueError(f"kunde_id darf für objekttyp={self.objekttyp} nicht gesetzt sein")
        if self.objekttyp != "kundenanlage" and self.standort_id is not None:
            raise ValueError(f"standort_id darf für objekttyp={self.objekttyp} nicht gesetzt sein")
        return self


class AnlageUpdate(BaseModel):
    standort_id: UUID | None = None
    bezeichnung: str | None = None
    adresse: dict | None = None
    anlagentyp: str | None = None
    qr_code: str | None = None
    hersteller: str | None = None
    modell: str | None = None
    seriennummer: str | None = None
    anschaffungsdatum: date | None = None
    notiz: str | None = None
    stammdaten: dict | None = None
    geo_lat: float | None = None
    geo_lng: float | None = None
    aktiv: bool | None = None


class AnlageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kunde_id: UUID | None
    standort_id: UUID | None
    objekttyp: AnlagenObjekttyp
    bezeichnung: str
    adresse: dict
    anlagentyp: str | None
    qr_code: str | None
    hersteller: str | None
    modell: str | None
    seriennummer: str | None
    anschaffungsdatum: date | None
    notiz: str | None
    stammdaten: dict
    geo_lat: float | None
    geo_lng: float | None
    aktiv: bool
    erstellt_von_kundenportal_zugang_id: UUID | None
    created_at: datetime
    updated_at: datetime
