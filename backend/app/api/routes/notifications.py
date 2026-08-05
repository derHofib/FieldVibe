from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.notification import Notification
from app.schemas.notification import NotificationRead

router = APIRouter(
    prefix="/api/notifications",
    tags=["notifications"],
    dependencies=[Depends(require_roles("mandant_admin", "custom"))],
)


@router.get("", response_model=list[NotificationRead])
async def list_notifications(
    nur_ungelesen: bool = Query(default=False),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Notification]:
    stmt = (
        select(Notification)
        .where(Notification.user_id == auth.user_id)
        .order_by(Notification.id.desc())
    )
    if nur_ungelesen:
        stmt = stmt.where(Notification.gelesen_am.is_(None))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("/{notification_id}/gelesen", response_model=NotificationRead)
async def mark_read(
    notification_id: int,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Notification:
    notification = await session.get(Notification, notification_id)
    if notification is None or notification.user_id != auth.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Benachrichtigung nicht gefunden"
        )
    if notification.gelesen_am is None:
        notification.gelesen_am = datetime.now(timezone.utc)
        await session.flush()
        await session.refresh(notification)
    return notification


@router.post("/gelesen", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(
    auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> None:
    await session.execute(
        update(Notification)
        .where(Notification.user_id == auth.user_id, Notification.gelesen_am.is_(None))
        .values(gelesen_am=datetime.now(timezone.utc))
    )
