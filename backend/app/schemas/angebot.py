from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.services.steuer_service import runde_cent

AngebotPositionstyp = Literal["material", "arbeitszeit"]
ERLAUBTE_MWST_SAETZE = (Decimal("19.00"), Decimal("7.00"), Decimal("0.00"))


def _pruefe_mwst_satz(wert: Decimal | None) -> Decimal | None:
    if wert is not None and wert not in ERLAUBTE_MWST_SAETZE:
        raise ValueError("Steuersatz muss 19, 7 oder 0 sein")
    return wert


class AngebotPositionCreate(BaseModel):
    artikelnummer: str | None = None
    beschreibung: str
    menge: Decimal = Decimal("1")
    einheit: str = "Stk"
    einzelpreis: Decimal = Decimal("0")
    positionstyp: AngebotPositionstyp = "material"


class AngebotPositionUpdate(BaseModel):
    artikelnummer: str | None = None
    beschreibung: str | None = Field(default=None, min_length=1)
    menge: Decimal | None = Field(default=None, gt=0)
    einheit: str | None = Field(default=None, min_length=1)
    einzelpreis: Decimal | None = Field(default=None, ge=0)
    positionstyp: AngebotPositionstyp | None = None

    @model_validator(mode="after")
    def _kein_explizites_null(self) -> "AngebotPositionUpdate":
        # Nur die Artikelnummer ist leerbar; bei den Pflichtfeldern wuerde ein
        # explizites null sonst stillschweigend ignoriert statt abgelehnt.
        for feld in ("beschreibung", "menge", "einheit", "einzelpreis", "positionstyp"):
            if feld in self.model_fields_set and getattr(self, feld) is None:
                raise ValueError(f"{feld} darf nicht leer sein")
        return self


class AngebotPositionenNeuOrdnen(BaseModel):
    position_ids: list[UUID]


class AngebotPositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position: int
    artikelnummer: str | None
    beschreibung: str
    menge: Decimal
    einheit: str
    einzelpreis: Decimal
    positionstyp: AngebotPositionstyp

    @computed_field  # type: ignore[prop-decorator]
    @property
    def gesamt(self) -> Decimal:
        return runde_cent(self.menge * self.einzelpreis)


class AngebotCreate(BaseModel):
    kunde_id: UUID
    vorgang_id: UUID | None = None
    gueltig_bis: date | None = None
    # None = Standard (19 %, beim Kleinunternehmer 0 %).
    mwst_satz: Decimal | None = None
    positionen: list[AngebotPositionCreate] = Field(default_factory=list)

    _mwst_satz_erlaubt = field_validator("mwst_satz")(_pruefe_mwst_satz)


class AngebotAusMaengelnCreate(BaseModel):
    mangel_ids: list[UUID]
    gueltig_bis: date | None = None


class AngebotAusMaterialBedarfenCreate(BaseModel):
    material_bedarf_ids: list[UUID]
    gueltig_bis: date | None = None


class AngebotAusVorgangCreate(BaseModel):
    vorgang_id: UUID
    gueltig_bis: date | None = None


class AngebotUpdate(BaseModel):
    status: str | None = None
    gueltig_bis: date | None = None
    mwst_satz: Decimal | None = None

    _mwst_satz_erlaubt = field_validator("mwst_satz")(_pruefe_mwst_satz)


class AngebotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kunde_id: UUID
    vorgang_id: UUID | None
    angebotsnummer: str
    status: str
    mwst_satz: Decimal
    gueltig_bis: date | None
    erstellt_von: UUID
    versendet_am: datetime | None
    angenommen_am: datetime | None
    abgelehnt_am: datetime | None
    auftrag_vorgang_id: UUID | None
    nachgefasst_am: datetime | None
    created_at: datetime
    updated_at: datetime
    positionen: list[AngebotPositionRead]
    gesamt_netto: Decimal
    gesamt_brutto: Decimal
    ist_abgelaufen: bool
