from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.vorgang_event import VorgangEventCreate, VorgangEventRead
from app.services import storage_service
from app.services.event_bus import event_bus
from app.services.mention_service import extract_and_notify_mentions
from app.services.photo_service import make_thumbnail
from app.services.vorgang_event_service import to_read_model as _to_read_model

router = APIRouter(
    prefix="/api/vorgaenge/{vorgang_id}/events",
    tags=["vorgang-events"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)

MAX_UPLOAD_BYTES = 15 * 1024 * 1024


async def _require_own_vorgang(session: AsyncSession, vorgang_id: UUID) -> Vorgang:
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
    return vorgang


@router.get("", response_model=list[VorgangEventRead])
async def list_events(vorgang_id: UUID, session: AsyncSession = Depends(get_db)) -> list[VorgangEventRead]:
    await _require_own_vorgang(session, vorgang_id)
    result = await session.execute(
        select(VorgangEvent)
        .where(VorgangEvent.vorgang_id == vorgang_id)
        .order_by(VorgangEvent.id.desc())
    )
    return [_to_read_model(e) for e in result.scalars().all()]


@router.post("", response_model=VorgangEventRead, status_code=status.HTTP_201_CREATED)
async def create_event(
    vorgang_id: UUID,
    body: VorgangEventCreate,
    response: Response,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorgangEventRead:
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
            return _to_read_model(existing_event)

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

    return _to_read_model(event)


@router.post("/foto", response_model=VorgangEventRead, status_code=status.HTTP_201_CREATED)
async def upload_foto(
    vorgang_id: UUID,
    file: UploadFile,
    kundensichtbar: bool = Form(default=False),
    body: str | None = Form(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorgangEventRead:
    await _require_own_vorgang(session, vorgang_id)

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Nur Bilddateien werden unterstützt"
        )

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Datei zu groß (max. 15 MB)"
        )

    # "Reduzierte Aufloesung" (Abschnitt 6) wird beim Upload einmal serverseitig
    # erzeugt statt bei jedem Abruf neu -- Feed-Vorschau und Offline-Cache in
    # der PWA laden dieselbe kleine Datei statt das Original zu skalieren.
    thumbnail = await make_thumbnail(data)

    key = storage_service.new_object_key(vorgang_id, file.filename or "foto.jpg")
    thumbnail_key = f"{key.rsplit('.', 1)[0]}_thumb.jpg"

    await storage_service.upload_bytes(key, data, file.content_type)
    await storage_service.upload_bytes(thumbnail_key, thumbnail, "image/jpeg")

    event = VorgangEvent(
        mandant_id=auth.mandant_id,
        vorgang_id=vorgang_id,
        event_type="foto",
        author_user_id=auth.user_id,
        body=body,
        payload={
            "key": key,
            "thumbnail_key": thumbnail_key,
            "content_type": file.content_type,
            "size": len(data),
        },
        kundensichtbar=kundensichtbar,
    )
    session.add(event)
    await session.flush()

    await event_bus.publish(
        auth.mandant_id,
        "vorgang_event",
        {"vorgang_id": str(vorgang_id), "event_id": event.id, "event_type": "foto"},
    )

    return _to_read_model(event)
