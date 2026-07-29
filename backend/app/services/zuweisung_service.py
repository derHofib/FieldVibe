from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kunde_zuweisung import KundeZuweisung

# Techniker sehen -- anders als mandant_admin/disponent -- nur Kunden, denen
# sie explizit zugewiesen sind (siehe kunden.py/anlagen.py/vorgaenge.py/
# feed.py/search.py). Diese Einschraenkung ist eine fachliche Sichtbarkeits-
# regel, keine Mandanten-Isolation, und laeuft daher bewusst auf
# Anwendungsebene statt per RLS -- RLS bleibt fuer die haerte
# Mandantengrenze reserviert.


async def assigned_kunde_ids(session: AsyncSession, user_id: UUID) -> set[UUID]:
    result = await session.execute(
        select(KundeZuweisung.kunde_id).where(KundeZuweisung.user_id == user_id)
    )
    return set(result.scalars().all())
