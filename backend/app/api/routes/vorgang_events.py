from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.vorgang_event import VorgangEventCreate, VorgangEventRead
from app.services.event_bus import event_bus
from app.services.mention_service import extract_and_notify_mentions

router = APIRouter(
    prefix="/api/vorgaenge/{vorgang_id}/events",
    tags=["vorgang-events"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)


async def _require_own_vorgang(session: AsyncSession, vorgang_id: UUID) -> Vorgang:
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
    return vorgang


@router.get("", response_model=list[VorgangEventRead])
async def list_events(vorgang_id: UUID, session: AsyncSession = Depends(get_db)) -> list[VorgangEvent]:
    await _require_own_vorgang(session, vorgang_id)
    result = await session.execute(
        select(VorgangEvent)
        .where(VorgangEvent.vorgang_id == vorgang_id)
        .order_by(VorgangEvent.id.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=VorgangEventRead, status_code=status.HTTP_201_CREATED)
async def create_event(
    vorgang_id: UUID,
    body: VorgangEventCreate,
    response: Response,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorgangEvent:
    vorgang = await _require_own_vorgang(session, vorgang_id)

    if body.client_uuid is not None:
        # Checked up front rather than caught as an IntegrityError after the
        # fact: a failed flush would abort the whole request transaction
        # (events share it with everything else this request touches), and
        # this is the common case anyway -- an offline-sync retry of an
        # already-accepted event, not a genuine concurrent collision.
        existing = await session.execute(
            select(VorgangEvent).where(VorgangEvent.client_uuid == body.client_uuid)
        )
        existing_event = existing.scalar_one_or_none()
        if existing_event is not None:
            response.status_code = status.HTTP_200_OK
            return existing_event

    event = VorgangEvent(
        mandant_id=auth.mandant_id,
        vorgang_id=vorgang_id,
        event_type=body.event_type,
        author_user_id=auth.user_id,
        body=body.body,
        payload=body.payload,
        ref_entity_type=body.ref_entity_type,
        ref_entity_id=body.ref_entity_id,
        kundensichtbar=body.kundensichtbar,
        client_uuid=body.client_uuid,
    )
    session.add(event)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Event-Konflikt"
        ) from exc

    if body.body:
        await extract_and_notify_mentions(
            session,
            mandant_id=auth.mandant_id,
            vorgang=vorgang,
            body=body.body,
            actor_user_id=auth.user_id,
        )

    await event_bus.publish(
        auth.mandant_id,
        "vorgang_event",
        {
            "vorgang_id": str(vorgang_id),
            "event_id": event.id,
            "event_type": event.event_type,
        },
    )

    return event
