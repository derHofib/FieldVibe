from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

LvKalkulationsmodus = Literal["festpreis", "berechnet"]


class LeistungsverzeichnisCreate(BaseModel):
    name: str
    beschreibung: str | None = None
    # Leer -> gilt fuer alle Kunden; sonst einem oder mehreren zugewiesen.
    kunden_ids: list[UUID] = []


class LeistungsverzeichnisUpdate(BaseModel):
    name: str | None = None
    beschreibung: str | None = None
    kunden_ids: list[UUID] | None = None


class LeistungsverzeichnisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    beschreibung: str | None
    kunden_ids: list[UUID] = []
    created_at: datetime
    updated_at: datetime


class MaterialPosten(BaseModel):
    bezeichnung: str
    menge: Decimal = Field(gt=0)
    einzelpreis: Decimal
    material_id: UUID | None = None


class LeistungsverzeichnisPositionCreate(BaseModel):
    # Nur bei eigenstaendigen Positionen (kein eltern_position_id) noetig --
    # bei einem Unterpunkt wird das LV vom Hauptpunkt uebernommen, siehe
    # app/api/routes/leistungsverzeichnis.py:create_position.
    leistungsverzeichnis_id: UUID | None = None
    eltern_position_id: UUID | None = None
    bezeichnung: str
    einheit: str = "Stk"
    einzelpreis: Decimal = Decimal("0")
    ist_stundensatz: bool = False
    notiz: str | None = None
    kalkulationsmodus: LvKalkulationsmodus = "festpreis"
    lohn_minuten: int | None = None
    lohn_stundensatz: Decimal | None = None
    lohn_gemeinkosten_prozent: Decimal | None = None
    material_posten: list[MaterialPosten] = []
    material_aufschlag_prozent: Decimal = Decimal("0")
    gewinn_wagnis_prozent: Decimal | None = None


class LeistungsverzeichnisPositionUpdate(BaseModel):
    # eltern_position_id und leistungsverzeichnis_id sind absichtlich nicht
    # aenderbar -- eine Position wechselt nach dem Anlegen nicht Hauptpunkt
    # oder LV, das vermeidet Sonderfaelle bei der Neuberechnung.
    bezeichnung: str | None = None
    einheit: str | None = None
    einzelpreis: Decimal | None = None
    ist_stundensatz: bool | None = None
    notiz: str | None = None
    kalkulationsmodus: LvKalkulationsmodus | None = None
    lohn_minuten: int | None = None
    lohn_stundensatz: Decimal | None = None
    lohn_gemeinkosten_prozent: Decimal | None = None
    material_posten: list[MaterialPosten] | None = None
    material_aufschlag_prozent: Decimal | None = None
    gewinn_wagnis_prozent: Decimal | None = None


class LeistungsverzeichnisPositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    leistungsverzeichnis_id: UUID
    eltern_position_id: UUID | None
    bezeichnung: str
    einheit: str
    einzelpreis: Decimal
    ist_stundensatz: bool
    notiz: str | None
    kalkulationsmodus: LvKalkulationsmodus
    lohn_minuten: int | None
    lohn_stundensatz: Decimal | None
    lohn_gemeinkosten_prozent: Decimal
    material_posten: list[MaterialPosten]
    material_aufschlag_prozent: Decimal
    gewinn_wagnis_prozent: Decimal
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
