from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def log_action(
    session: AsyncSession,
    *,
    aktion: str,
    mandant_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    payload: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        aktion=aktion,
        mandant_id=mandant_id,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
    )
    session.add(entry)
    await session.flush()
    return entry
