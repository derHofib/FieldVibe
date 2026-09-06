from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

LvKalkulationsmodus = Literal["festpreis", "berechnet"]


class MaterialPosten(BaseModel):
    bezeichnung: str
    menge: Decimal = Field(gt=0)
    einzelpreis: Decimal
    material_id: UUID | None = None


class LeistungsverzeichnisPositionCreate(BaseModel):
    # kunde_id=None -> gilt fuer alle Kunden (mandantenweiter Katalog).
    kunde_id: UUID | None = None
    # eltern_position_id gesetzt -> Unterpunkt; kunde_id wird dann serverseitig
    # vom Hauptpunkt uebernommen (siehe Route), ein hier mitgeschicktes
    # kunde_id wird ignoriert.
    eltern_position_id: UUID | None = None
    bezeichnung: str
    einheit: str = "Stk"
    einzelpreis: Decimal = Decimal("0")
    ist_stundensatz: bool = False
    notiz: str | None = None
    kalkulationsmodus: LvKalkulationsmodus = "festpreis"
    lohn_minuten: int | None = None
    lohn_stundensatz: Decimal | None = None
    material_posten: list[MaterialPosten] = []
    material_aufschlag_prozent: Decimal = Decimal("0")


class LeistungsverzeichnisPositionUpdate(BaseModel):
    # eltern_position_id ist absichtlich nicht aenderbar -- ein Unterpunkt
    # wechselt nach dem Anlegen nicht den Hauptpunkt, das vermeidet
    # Sonderfaelle bei der Neuberechnung.
    kunde_id: UUID | None = None
    bezeichnung: str | None = None
    einheit: str | None = None
    einzelpreis: Decimal | None = None
    ist_stundensatz: bool | None = None
    notiz: str | None = None
    kalkulationsmodus: LvKalkulationsmodus | None = None
    lohn_minuten: int | None = None
    lohn_stundensatz: Decimal | None = None
    material_posten: list[MaterialPosten] | None = None
    material_aufschlag_prozent: Decimal | None = None


class LeistungsverzeichnisPositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kunde_id: UUID | None
    eltern_position_id: UUID | None
    bezeichnung: str
    einheit: str
    einzelpreis: Decimal
    ist_stundensatz: bool
    notiz: str | None
    kalkulationsmodus: LvKalkulationsmodus
    lohn_minuten: int | None
    lohn_stundensatz: Decimal | None
    material_posten: list[MaterialPosten]
    material_aufschlag_prozent: Decimal
    lohn_gesamt: Decimal
    material_gesamt: Decimal
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
