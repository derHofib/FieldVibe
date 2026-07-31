from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_module, require_roles
from app.models.pruefmittel import PRUEFMITTEL_STATUS, Pruefmittel
from app.models.user import User
from app.schemas.pruefmittel import PruefmittelCreate, PruefmittelRead, PruefmittelUpdate
from app.services.date_utils import add_months

router = APIRouter(
    prefix="/api/pruefmittel",
    tags=["pruefmittel"],
    dependencies=[
        Depends(require_roles("mandant_admin", "disponent", "techniker")),
        Depends(require_module("pruefzyklen")),
    ],
)


@router.get("", response_model=list[PruefmittelRead])
async def list_pruefmittel(
    zugewiesen_an: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> list[Pruefmittel]:
    stmt = select(Pruefmittel).order_by(Pruefmittel.naechste_kalibrierung_am.asc())
    if zugewiesen_an:
        stmt = stmt.where(Pruefmittel.zugewiesen_an == zugewiesen_an)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _validate_zugewiesen_an(session: AsyncSession, user_id: UUID | None) -> None:
    if user_id is None:
        return
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Techniker nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )


@router.post(
    "",
    response_model=PruefmittelRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_pruefmittel(
    body: PruefmittelCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Pruefmittel:
    await _validate_zugewiesen_an(session, body.zugewiesen_an)

    basis = body.letzte_kalibrierung_am or datetime.now(timezone.utc).date()
    pruefmittel = Pruefmittel(
        mandant_id=auth.mandant_id,
        bezeichnung=body.bezeichnung,
        seriennummer=body.seriennummer,
        zugewiesen_an=body.zugewiesen_an,
        kalibrierintervall_monate=body.kalibrierintervall_monate,
        letzte_kalibrierung_am=body.letzte_kalibrierung_am,
        naechste_kalibrierung_am=add_months(basis, body.kalibrierintervall_monate),
    )
    session.add(pruefmittel)
    await session.flush()
    await session.refresh(pruefmittel)
    return pruefmittel


@router.get("/{pruefmittel_id}", response_model=PruefmittelRead)
async def get_pruefmittel(
    pruefmittel_id: UUID, session: AsyncSession = Depends(get_db)
) -> Pruefmittel:
    pruefmittel = await session.get(Pruefmittel, pruefmittel_id)
    if pruefmittel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prüfmittel nicht gefunden"
        )
    return pruefmittel


@router.patch(
    "/{pruefmittel_id}",
    response_model=PruefmittelRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def update_pruefmittel(
    pruefmittel_id: UUID,
    body: PruefmittelUpdate,
    session: AsyncSession = Depends(get_db),
) -> Pruefmittel:
    pruefmittel = await session.get(Pruefmittel, pruefmittel_id)
    if pruefmittel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prüfmittel nicht gefunden"
        )

    changes = body.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] not in PRUEFMITTEL_STATUS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ungültiger Status")
    if "zugewiesen_an" in changes:
        await _validate_zugewiesen_an(session, changes["zugewiesen_an"])

    letzte_kalibrierung_explizit_gesetzt = "letzte_kalibrierung_am" in changes
    naechste_kalibrierung_explizit_gesetzt = "naechste_kalibrierung_am" in changes

    for field, value in changes.items():
        setattr(pruefmittel, field, value)

    if letzte_kalibrierung_explizit_gesetzt and not naechste_kalibrierung_explizit_gesetzt:
        basis: date = pruefmittel.letzte_kalibrierung_am or datetime.now(timezone.utc).date()
        pruefmittel.naechste_kalibrierung_am = add_months(
            basis, pruefmittel.kalibrierintervall_monate
        )

    await session.flush()
    await session.refresh(pruefmittel)
    return pruefmittel
