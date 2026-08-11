from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class UstVaSatzZeile(BaseModel):
    satz: Decimal
    netto: Decimal
    steuer: Decimal


class UstVaBericht(BaseModel):
    von: date
    bis: date
    umsatzsteuer_saetze: list[UstVaSatzZeile]
    vorsteuer_saetze: list[UstVaSatzZeile]
    summe_umsatzsteuer: Decimal
    summe_vorsteuer: Decimal
    # Positiv: Zahllast an das Finanzamt. Negativ: Vorsteuerueberhang
    # (Erstattung).
    zahllast: Decimal


class OffenerPostenEintrag(BaseModel):
    id: UUID
    nummer: str
    partner_name: str
    faellig_am: date | None
    # 0, solange noch nicht faellig oder kein Faelligkeitsdatum hinterlegt.
    tage_ueberfaellig: int
    offener_betrag: Decimal


class OffenePostenBucket(BaseModel):
    label: str
    anzahl: int
    summe: Decimal


class OffenePostenBericht(BaseModel):
    debitoren: list[OffenerPostenEintrag]
    kreditoren: list[OffenerPostenEintrag]
    summe_debitoren: Decimal
    summe_kreditoren: Decimal
    debitoren_buckets: list[OffenePostenBucket]
    kreditoren_buckets: list[OffenePostenBucket]
