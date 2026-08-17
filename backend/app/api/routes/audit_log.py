from datetime import date, datetime, time, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.models.audit_log import AuditLog
from app.schemas.audit_log import AuditLogRead

router = APIRouter(
    prefix="/api/admin/audit-log",
    tags=["super-admin: audit-log"],
    dependencies=[Depends(require_roles("super_admin"))],
)


@router.get("", response_model=list[AuditLogRead])
async def list_audit_log(
    session: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, le=500, ge=1),
    mandant_id: UUID | None = None,
    aktion: str | None = None,
    von: date | None = None,
    bis: date | None = None,
) -> list[AuditLog]:
    stmt = select(AuditLog)
    if mandant_id is not None:
        stmt = stmt.where(AuditLog.mandant_id == mandant_id)
    if aktion:
        stmt = stmt.where(AuditLog.aktion.ilike(f"%{aktion}%"))
    if von is not None:
        stmt = stmt.where(AuditLog.created_at >= datetime.combine(von, time.min, tzinfo=timezone.utc))
    if bis is not None:
        stmt = stmt.where(AuditLog.created_at <= datetime.combine(bis, time.max, tzinfo=timezone.utc))
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())
