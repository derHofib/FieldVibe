from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.anlagen_feld_definition import AnlagenFeldDefinition
from app.schemas.anlagen_feld_definition import (
    AnlagenFeldDefinitionCreate,
    AnlagenFeldDefinitionRead,
    AnlagenFeldDefinitionUpdate,
)

router = APIRouter(
    prefix="/api/anlagen-feld-definitionen",
    tags=["anlagen-feld-definitionen"],
    dependencies=[
        Depends(require_roles("mandant_admin", "disponent", "techniker", "controller", "mitarbeiter"))
    ],
)


@router.get("", response_model=list[AnlagenFeldDefinitionRead])
async def list_anlagen_feld_definitionen(
    anlagentyp: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> list[AnlagenFeldDefinition]:
    stmt = select(AnlagenFeldDefinition).order_by(
        AnlagenFeldDefinition.anlagentyp, AnlagenFeldDefinition.reihenfolge
    )
    if anlagentyp:
        stmt = stmt.where(AnlagenFeldDefinition.anlagentyp == anlagentyp)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "",
    response_model=AnlagenFeldDefinitionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin"))],
)
async def create_anlagen_feld_definition(
    body: AnlagenFeldDefinitionCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AnlagenFeldDefinition:
    definition = AnlagenFeldDefinition(
        mandant_id=auth.mandant_id,
        anlagentyp=body.anlagentyp,
        feld_name=body.feld_name,
        feld_typ=body.feld_typ,
        reihenfolge=body.reihenfolge,
    )
    session.add(definition)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Es gibt bereits ein Feld mit diesem Namen für diesen Anlagentyp",
        ) from exc
    return definition


@router.patch(
    "/{definition_id}",
    response_model=AnlagenFeldDefinitionRead,
    dependencies=[Depends(require_roles("mandant_admin"))],
)
async def update_anlagen_feld_definition(
    definition_id: UUID,
    body: AnlagenFeldDefinitionUpdate,
    session: AsyncSession = Depends(get_db),
) -> AnlagenFeldDefinition:
    definition = await session.get(AnlagenFeldDefinition, definition_id)
    if definition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feld nicht gefunden")

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(definition, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Es gibt bereits ein Feld mit diesem Namen für diesen Anlagentyp",
        ) from exc
    if changes:
        await session.refresh(definition)
    return definition


@router.delete(
    "/{definition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("mandant_admin"))],
)
async def delete_anlagen_feld_definition(
    definition_id: UUID, session: AsyncSession = Depends(get_db)
) -> None:
    definition = await session.get(AnlagenFeldDefinition, definition_id)
    if definition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feld nicht gefunden")
    await session.delete(definition)
    await session.flush()
