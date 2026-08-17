from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.gespeicherter_filter import GespeicherterFilter
from app.schemas.gespeicherter_filter import (
    GespeicherterFilterCreate,
    GespeicherterFilterEntitaet,
    GespeicherterFilterRead,
    GespeicherterFilterUpdate,
)

router = APIRouter(
    prefix="/api/gespeicherte-filter",
    tags=["gespeicherte-filter"],
    dependencies=[Depends(require_roles("mandant_admin", "custom"))],
)


async def _unset_bisherigen_standard(
    session: AsyncSession, auth: AuthContext, entitaet: str, ausser_id: UUID | None = None
) -> None:
    # Nur eine Vorlage je Nutzer und Entitaet darf als Standard markiert
    # sein -- wird eine neue als Standard gesetzt, verliert die bisherige
    # diesen Status stillschweigend (kein Konflikt-Fehler, das waere fuer
    # eine simple Checkbox in der UI unpassend).
    stmt = select(GespeicherterFilter).where(
        GespeicherterFilter.user_id == auth.user_id,
        GespeicherterFilter.entitaet == entitaet,
        GespeicherterFilter.ist_standard.is_(True),
    )
    if ausser_id is not None:
        stmt = stmt.where(GespeicherterFilter.id != ausser_id)
    result = await session.execute(stmt)
    for bestehend in result.scalars().all():
        bestehend.ist_standard = False


@router.get("", response_model=list[GespeicherterFilterRead])
async def list_gespeicherte_filter(
    entitaet: GespeicherterFilterEntitaet | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[GespeicherterFilter]:
    stmt = (
        select(GespeicherterFilter)
        .where(GespeicherterFilter.user_id == auth.user_id)
        .order_by(GespeicherterFilter.name)
    )
    if entitaet:
        stmt = stmt.where(GespeicherterFilter.entitaet == entitaet)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=GespeicherterFilterRead, status_code=status.HTTP_201_CREATED)
async def create_gespeicherter_filter(
    body: GespeicherterFilterCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> GespeicherterFilter:
    if body.ist_standard:
        await _unset_bisherigen_standard(session, auth, body.entitaet)

    filter_ = GespeicherterFilter(
        mandant_id=auth.mandant_id,
        user_id=auth.user_id,
        entitaet=body.entitaet,
        name=body.name,
        filter_json=body.filter_json,
        ist_standard=body.ist_standard,
    )
    session.add(filter_)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Es gibt bereits eine Filter-Vorlage mit diesem Namen für diese Ansicht",
        ) from exc
    return filter_


async def _get_own_filter(
    session: AsyncSession, auth: AuthContext, filter_id: UUID
) -> GespeicherterFilter:
    filter_ = await session.get(GespeicherterFilter, filter_id)
    if filter_ is None or filter_.user_id != auth.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filter-Vorlage nicht gefunden")
    return filter_


@router.patch("/{filter_id}", response_model=GespeicherterFilterRead)
async def update_gespeicherter_filter(
    filter_id: UUID,
    body: GespeicherterFilterUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> GespeicherterFilter:
    filter_ = await _get_own_filter(session, auth, filter_id)

    changes = body.model_dump(exclude_unset=True)
    if changes.get("ist_standard"):
        await _unset_bisherigen_standard(session, auth, filter_.entitaet, ausser_id=filter_.id)
    for field, value in changes.items():
        setattr(filter_, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Es gibt bereits eine Filter-Vorlage mit diesem Namen für diese Ansicht",
        ) from exc
    if changes:
        await session.refresh(filter_)
    return filter_


@router.delete("/{filter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_gespeicherter_filter(
    filter_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    filter_ = await _get_own_filter(session, auth, filter_id)
    await session.delete(filter_)
    await session.flush()
