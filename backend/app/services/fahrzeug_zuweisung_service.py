from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fahrzeug_zuweisung import FahrzeugZuweisung
from app.models.user import User


async def assigned_fahrzeug_id(session: AsyncSession, user_id: UUID) -> UUID | None:
    result = await session.execute(
        select(FahrzeugZuweisung.anlage_id).where(FahrzeugZuweisung.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def technikern_zugewiesen(session: AsyncSession, anlage_id: UUID) -> list[User]:
    """Alle Techniker, denen genau dieses Fahrzeug aktuell zugewiesen ist --
    genutzt fuer Inventur-Erinnerungen, damit nicht nur Admin/Disponent,
    sondern auch der/die tatsaechliche(n) Fahrer benachrichtigt werden."""
    result = await session.execute(
        select(User)
        .join(FahrzeugZuweisung, FahrzeugZuweisung.user_id == User.id)
        .where(FahrzeugZuweisung.anlage_id == anlage_id)
    )
    return list(result.scalars().all())
