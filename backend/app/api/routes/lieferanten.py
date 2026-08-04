from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_module, require_roles
from app.models.lieferant import Lieferant
from app.schemas.lieferant import LieferantCreate, LieferantRead, LieferantUpdate

router = APIRouter(
    prefix="/api/lieferanten",
    tags=["lieferanten"],
    dependencies=[
        Depends(
            require_roles("mandant_admin", "disponent", "techniker", "controller", "mitarbeiter")
        ),
        Depends(require_module("material")),
    ],
)


@router.get("", response_model=list[LieferantRead])
async def list_lieferanten(session: AsyncSession = Depends(get_db)) -> list[Lieferant]:
    result = await session.execute(select(Lieferant).order_by(Lieferant.name))
    return list(result.scalars().all())


@router.post(
    "",
    response_model=LieferantRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_lieferant(
    body: LieferantCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Lieferant:
    lieferant = Lieferant(mandant_id=auth.mandant_id, **body.model_dump())
    session.add(lieferant)
    await session.flush()
    await session.refresh(lieferant)
    return lieferant


@router.patch(
    "/{lieferant_id}",
    response_model=LieferantRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def update_lieferant(
    lieferant_id: UUID, body: LieferantUpdate, session: AsyncSession = Depends(get_db)
) -> Lieferant:
    lieferant = await session.get(Lieferant, lieferant_id)
    if lieferant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lieferant nicht gefunden")

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(lieferant, field, value)
    await session.flush()
    if changes:
        await session.refresh(lieferant)
    return lieferant


@router.delete(
    "/{lieferant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def delete_lieferant(lieferant_id: UUID, session: AsyncSession = Depends(get_db)) -> None:
    lieferant = await session.get(Lieferant, lieferant_id)
    if lieferant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lieferant nicht gefunden")
    await session.delete(lieferant)
    await session.flush()
