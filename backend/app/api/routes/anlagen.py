from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.models.anlage import Anlage
from app.models.kunde import Kunde
from app.schemas.anlage import AnlageCreate, AnlageRead, AnlageUpdate

router = APIRouter(
    prefix="/api/anlagen",
    tags=["anlagen"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)


async def _require_own_kunde(session: AsyncSession, kunde_id: UUID) -> Kunde:
    # RLS already hides other tenants' rows from this SELECT, so a foreign
    # kunde_id resolves to None here -- this is what actually stops an
    # Anlage from being linked to another mandant's Kunde (the FK
    # constraint alone would not catch it: FK existence checks run with the
    # table owner's privileges and ignore RLS).
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kunde nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    return kunde


@router.get("", response_model=list[AnlageRead])
async def list_anlagen(
    kunde_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> list[Anlage]:
    stmt = select(Anlage).order_by(Anlage.bezeichnung)
    if kunde_id:
        stmt = stmt.where(Anlage.kunde_id == kunde_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "",
    response_model=AnlageRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_anlage(
    body: AnlageCreate,
    auth=Depends(require_roles("mandant_admin", "disponent")),
    session: AsyncSession = Depends(get_db),
) -> Anlage:
    await _require_own_kunde(session, body.kunde_id)

    anlage = Anlage(
        mandant_id=auth.mandant_id,
        kunde_id=body.kunde_id,
        bezeichnung=body.bezeichnung,
        adresse=body.adresse,
        anlagentyp=body.anlagentyp,
        qr_code=body.qr_code,
        stammdaten=body.stammdaten,
        geo_lat=body.geo_lat,
        geo_lng=body.geo_lng,
    )
    session.add(anlage)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="QR-Code bereits vergeben"
        ) from exc
    return anlage


@router.get("/{anlage_id}", response_model=AnlageRead)
async def get_anlage(anlage_id: UUID, session: AsyncSession = Depends(get_db)) -> Anlage:
    anlage = await session.get(Anlage, anlage_id)
    if anlage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anlage nicht gefunden")
    return anlage


@router.patch(
    "/{anlage_id}",
    response_model=AnlageRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def update_anlage(
    anlage_id: UUID, body: AnlageUpdate, session: AsyncSession = Depends(get_db)
) -> Anlage:
    anlage = await session.get(Anlage, anlage_id)
    if anlage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anlage nicht gefunden")

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(anlage, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="QR-Code bereits vergeben"
        ) from exc
    if changes:
        await session.refresh(anlage)
    return anlage
