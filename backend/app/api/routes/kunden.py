from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.kunde import Kunde
from app.schemas.kunde import KundeCreate, KundeRead, KundeUpdate
from app.services.numbering_service import next_kundennummer

# super_admin is deliberately excluded: fachliche Daten sind immer
# mandantengebunden, und ein nicht-impersonierender super_admin hat kein
# mandant_id im Token. Zugriff läuft für die Plattform-Rolle ausschließlich
# über "Login als Mandant" (das Token trägt dann role=mandant_admin).
router = APIRouter(
    prefix="/api/kunden",
    tags=["kunden"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)


@router.get("", response_model=list[KundeRead])
async def list_kunden(
    q: str | None = Query(default=None, description="Suche in Name/Kundennummer"),
    session: AsyncSession = Depends(get_db),
) -> list[Kunde]:
    stmt = select(Kunde).order_by(Kunde.name)
    if q:
        stmt = stmt.where(Kunde.name.ilike(f"%{q}%"))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "",
    response_model=KundeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_kunde(
    body: KundeCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Kunde:
    kundennummer = body.kundennummer or await next_kundennummer(session, auth.mandant_id)
    kunde = Kunde(
        mandant_id=auth.mandant_id,
        kundennummer=kundennummer,
        name=body.name,
        typ=body.typ,
        ansprechpartner=body.ansprechpartner,
        adresse=body.adresse,
        notiz=body.notiz,
    )
    session.add(kunde)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Kundennummer bereits vergeben"
        ) from exc
    return kunde


@router.get("/{kunde_id}", response_model=KundeRead)
async def get_kunde(kunde_id: UUID, session: AsyncSession = Depends(get_db)) -> Kunde:
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")
    return kunde


@router.patch(
    "/{kunde_id}",
    response_model=KundeRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def update_kunde(
    kunde_id: UUID, body: KundeUpdate, session: AsyncSession = Depends(get_db)
) -> Kunde:
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(kunde, field, value)
    await session.flush()
    if changes:
        await session.refresh(kunde)
    return kunde
