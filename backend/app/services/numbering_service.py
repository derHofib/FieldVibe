from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kunde import Kunde
from app.models.vorgang import Vorgang

# Kunden/Vorgaenge are never hard-deleted (GoBD-artige Aufbewahrungspflicht,
# siehe Abschnitt 11), so a simple per-mandant row count is a safe,
# collision-free basis for sequential numbers -- no gaps to worry about.


async def next_kundennummer(session: AsyncSession, mandant_id: UUID) -> str:
    count = await session.scalar(
        select(func.count()).select_from(Kunde).where(Kunde.mandant_id == mandant_id)
    )
    return f"K-{count + 1:05d}"


async def next_vorgangsnummer(session: AsyncSession, mandant_id: UUID) -> str:
    count = await session.scalar(
        select(func.count()).select_from(Vorgang).where(Vorgang.mandant_id == mandant_id)
    )
    return f"V-{count + 1:05d}"
