"""Einheitliche, rückwärtskompatible Paginierung für Listen-Endpunkte.

Ohne Parameter liefern die Endpunkte weiter "alles" -- aber höchstens
STANDARD_LIMIT Zeilen, damit ein wachsender Mandant keine unbegrenzten
Antworten erzeugt. Die Gesamtmenge steht im Header X-Total-Count; Clients, die
mehr brauchen, blättern per offset.
"""

from dataclasses import dataclass

from fastapi import Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

STANDARD_LIMIT = 1000
MAX_LIMIT = 1000
TOTAL_COUNT_HEADER = "X-Total-Count"


@dataclass(frozen=True)
class Seite:
    limit: int
    offset: int


def seitenparameter(
    limit: int = Query(default=STANDARD_LIMIT, ge=1, le=MAX_LIMIT, description="Maximale Zeilenzahl"),
    offset: int = Query(default=0, ge=0, description="Anzahl zu überspringender Zeilen"),
) -> Seite:
    return Seite(limit=limit, offset=offset)


async def seite_laden(session: AsyncSession, stmt: Select, seite: Seite, response: Response) -> list:
    """Führt die Abfrage seitenweise aus und setzt X-Total-Count. Die Sortierung
    der Abfrage muss eindeutig sein (id als Tiebreaker), sonst wackelt die
    Seitengrenze bei gleichen Sortierwerten."""
    gesamt = (
        await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))
    ).scalar_one()
    response.headers[TOTAL_COUNT_HEADER] = str(gesamt)
    result = await session.execute(stmt.limit(seite.limit).offset(seite.offset))
    return list(result.scalars().all())
