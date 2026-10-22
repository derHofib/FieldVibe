from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AuthContext,
    get_current_user,
    get_db,
    require_module,
    require_recht,
    require_roles,
)
from app.api.paginierung import Seite, seite_laden, seitenparameter
from app.models.lieferant import Lieferant
from app.schemas.lieferant import LieferantCreate, LieferantRead, LieferantUpdate
from app.services import datev_service, papierkorb_service

router = APIRouter(
    prefix="/api/lieferanten",
    tags=["lieferanten"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_module("material")),
    ],
)


async def _kreditorenkonto_pruefen(session: AsyncSession, mandant_id: UUID, konto: str) -> None:
    try:
        await datev_service.personenkonto_fuer_mandant_pruefen(session, mandant_id, konto, "kreditor")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


async def _flush_mit_kontofehler(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Kreditorenkonto bereits vergeben") from exc


@router.get(
    "", response_model=list[LieferantRead], dependencies=[Depends(require_recht("material", "sehen"))]
)
async def list_lieferanten(
    response: Response,
    seite: Seite = Depends(seitenparameter),
    session: AsyncSession = Depends(get_db),
) -> list[Lieferant]:
    stmt = select(Lieferant).where(Lieferant.geloescht_am.is_(None)).order_by(Lieferant.name, Lieferant.id)
    return await seite_laden(session, stmt, seite, response)


@router.post(
    "",
    response_model=LieferantRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("material", "erstellen")),
    ],
)
async def create_lieferant(
    body: LieferantCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Lieferant:
    if body.kreditorenkonto:
        await _kreditorenkonto_pruefen(session, auth.mandant_id, body.kreditorenkonto)
    lieferant = Lieferant(mandant_id=auth.mandant_id, **body.model_dump())
    session.add(lieferant)
    await _flush_mit_kontofehler(session)
    await session.refresh(lieferant)
    return lieferant


@router.patch(
    "/{lieferant_id}",
    response_model=LieferantRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("material", "bearbeiten")),
    ],
)
async def update_lieferant(
    lieferant_id: UUID,
    body: LieferantUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Lieferant:
    lieferant = await session.get(Lieferant, lieferant_id)
    if lieferant is None or lieferant.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lieferant nicht gefunden")

    changes = body.model_dump(exclude_unset=True)
    if changes.get("kreditorenkonto"):
        await _kreditorenkonto_pruefen(session, auth.mandant_id, changes["kreditorenkonto"])
    for field, value in changes.items():
        setattr(lieferant, field, value)
    await _flush_mit_kontofehler(session)
    if changes:
        await session.refresh(lieferant)
    return lieferant


@router.delete(
    "/{lieferant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("material", "loeschen")),
    ],
)
async def delete_lieferant(
    lieferant_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    # Papierkorb statt Hard-Delete: kaskadiert auf Bestellungen dieses
    # Lieferanten (siehe app/services/papierkorb_service.py).
    lieferant = await papierkorb_service.soft_delete(
        session, entity_typ="lieferant", entity_id=lieferant_id, actor_user_id=auth.user_id
    )
    if lieferant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lieferant nicht gefunden")
