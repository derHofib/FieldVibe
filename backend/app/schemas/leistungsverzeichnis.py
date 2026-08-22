from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LeistungsverzeichnisPositionCreate(BaseModel):
    kunde_id: UUID
    bezeichnung: str
    einheit: str = "Stk"
    einzelpreis: Decimal = Decimal("0")
    ist_stundensatz: bool = False
    notiz: str | None = None


class LeistungsverzeichnisPositionUpdate(BaseModel):
    bezeichnung: str | None = None
    einheit: str | None = None
    einzelpreis: Decimal | None = None
    ist_stundensatz: bool | None = None
    notiz: str | None = None


class LeistungsverzeichnisPositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kunde_id: UUID
    bezeichnung: str
    einheit: str
    einzelpreis: Decimal
    ist_stundensatz: bool
    notiz: str | None
    created_at: datetime
    updated_at: datetime


class LeistungsverzeichnisVerwendungCreate(BaseModel):
    vorgang_id: UUID
    menge: Decimal = Field(gt=0)


class LeistungsverzeichnisVerwendungRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lv_position_id: UUID
    vorgang_id: UUID
    menge: Decimal
    verwendet_von: UUID
    created_at: datetime


class LeistungsverzeichnisVerwendungMitDetails(LeistungsverzeichnisVerwendungRead):
    lv_bezeichnung: str
    lv_einheit: str
    lv_einzelpreis: Decimal
