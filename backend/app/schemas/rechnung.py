from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field


class RechnungCreate(BaseModel):
    kunde_id: UUID
    vorgang_id: UUID | None = None
    betrag_netto: Decimal
    mwst_satz: Decimal = Decimal("19.00")
    faellig_am: date | None = None


class RechnungUpdate(BaseModel):
    status: str | None = None
    betrag_netto: Decimal | None = None
    faellig_am: date | None = None


class RechnungRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kunde_id: UUID
    vorgang_id: UUID | None
    rechnungsnummer: str
    betrag_netto: Decimal
    mwst_satz: Decimal
    status: str
    faellig_am: date | None
    erstellt_von: UUID
    versendet_am: datetime | None
    bezahlt_am: datetime | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def betrag_brutto(self) -> Decimal:
        return (self.betrag_netto + self.betrag_netto * self.mwst_satz / Decimal("100")).quantize(Decimal("0.01"))
