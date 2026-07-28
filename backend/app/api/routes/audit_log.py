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
) -> list[AuditLog]:
    result = await session.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())
