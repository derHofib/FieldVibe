"""Uebersicht und Neustart fehlgeschlagener Mails (Mail-Outbox, siehe
app/services/mail_outbox_service.py und docs/BETRIEB.md). Nur Administratoren; die
RLS der Sitzung beschraenkt einen Mandanten-Admin auf seine eigenen Mails."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.models.mail_outbox import MailOutbox
from app.schemas.mail_outbox import MailOutboxRead, OutboxStatus
from app.services import mail_outbox_service

router = APIRouter(
    prefix="/api/mail-outbox",
    tags=["mail-outbox"],
    dependencies=[Depends(require_roles("mandant_admin", "super_admin"))],
)


def _read(row: MailOutbox) -> MailOutboxRead:
    return MailOutboxRead(
        id=row.id,
        mandant_id=row.mandant_id,
        email_log_id=row.email_log_id,
        empfaenger=row.empfaenger,
        betreff=row.betreff,
        status=row.status,
        versuche=row.versuche,
        naechster_versuch_am=row.naechster_versuch_am,
        letzter_fehler=row.letzter_fehler,
        anhang_anzahl=len(row.anhaenge or []),
        created_at=row.created_at,
        gesendet_am=row.gesendet_am,
    )


@router.get("", response_model=list[MailOutboxRead])
async def list_mail_outbox(
    status_filter: OutboxStatus = Query("failed", alias="status"),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> list[MailOutboxRead]:
    zeilen = (await session.execute(
        select(MailOutbox).where(MailOutbox.status == status_filter).order_by(MailOutbox.created_at.desc()).limit(limit)
    )).scalars().all()
    return [_read(z) for z in zeilen]


@router.post("/{outbox_id}/wiederholen", response_model=MailOutboxRead)
async def mail_erneut_senden(outbox_id: UUID, session: AsyncSession = Depends(get_db)) -> MailOutboxRead:
    row = await mail_outbox_service.wiederholen(session, outbox_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Keine fehlgeschlagene Mail mit dieser ID")
    return _read(row)
