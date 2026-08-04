from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.tag import Tag, TagAssignment
from app.schemas.tag import TagAssignmentCreate, TagAssignmentRead, TagCreate, TagRead
from app.services import papierkorb_service

# loesch_operativ hat ueberall dieselben Rechte wie mandant_admin (siehe
# app/api/deps.py:require_roles()) und braucht daher wie dieser Zugriff auf
# diesen Router.
router = APIRouter(
    prefix="/api/tags",
    tags=["tags"],
    dependencies=[
        Depends(require_roles("mandant_admin", "disponent", "techniker", "loesch_operativ"))
    ],
)


def _normalize_label(label: str) -> str:
    return label.strip().lstrip("#").lower()


@router.get("", response_model=list[TagRead])
async def list_tags(session: AsyncSession = Depends(get_db)) -> list[Tag]:
    result = await session.execute(
        select(Tag).where(Tag.geloescht_am.is_(None)).order_by(Tag.label)
    )
    return list(result.scalars().all())


@router.post(
    "",
    response_model=TagRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_tag(
    body: TagCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Tag:
    tag = Tag(mandant_id=auth.mandant_id, label=_normalize_label(body.label), farbe=body.farbe)
    session.add(tag)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Tag existiert bereits"
        ) from exc
    return tag


@router.delete(
    "/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "loesch_operativ"))],
)
async def delete_tag(
    tag_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    tag = await session.get(Tag, tag_id)
    if tag is None or tag.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag nicht gefunden")
    if tag.system_tag:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System-Tags können nicht gelöscht werden",
        )
    await papierkorb_service.soft_delete(
        session, entity_typ="tag", entity_id=tag_id, actor_user_id=auth.user_id
    )


@router.get("/assignments", response_model=list[TagAssignmentRead])
async def list_assignments(
    entity_type: str = Query(...),
    entity_id: UUID = Query(...),
    session: AsyncSession = Depends(get_db),
) -> list[TagAssignment]:
    result = await session.execute(
        select(TagAssignment).where(
            TagAssignment.entity_type == entity_type, TagAssignment.entity_id == entity_id
        )
    )
    return list(result.scalars().all())


@router.post(
    "/{tag_id}/assignments",
    response_model=TagAssignmentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)
async def assign_tag(
    tag_id: UUID,
    body: TagAssignmentCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> TagAssignment:
    tag = await session.get(Tag, tag_id)
    if tag is None or tag.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag nicht gefunden")

    assignment = TagAssignment(
        tag_id=tag_id,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        mandant_id=auth.mandant_id,
    )
    session.add(assignment)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Tag bereits zugewiesen"
        ) from exc
    return assignment


@router.delete(
    "/{tag_id}/assignments",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)
async def unassign_tag(
    tag_id: UUID,
    entity_type: str = Query(...),
    entity_id: UUID = Query(...),
    session: AsyncSession = Depends(get_db),
) -> None:
    await session.execute(
        delete(TagAssignment).where(
            TagAssignment.tag_id == tag_id,
            TagAssignment.entity_type == entity_type,
            TagAssignment.entity_id == entity_id,
        )
    )
