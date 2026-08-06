from datetime import date
from decimal import Decimal

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
