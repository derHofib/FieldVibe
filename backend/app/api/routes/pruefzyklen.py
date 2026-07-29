from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.anlage import Anlage
from app.models.pruefzyklus import Pruefzyklus
from app.schemas.pruefzyklus import PruefzyklusCreate, PruefzyklusRead, PruefzyklusUpdate
from app.services.date_utils import add_months

router = APIRouter(
    prefix="/api/pruefzyklen",
    tags=["pruefzyklen"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)


@router.get("", response_model=list[PruefzyklusRead])
async def list_pruefzyklen(
    anlage_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> list[Pruefzyklus]:
    stmt = select(Pruefzyklus).order_by(Pruefzyklus.naechste_pruefung_am.asc())
    if anlage_id:
        stmt = stmt.where(Pruefzyklus.anlage_id == anlage_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "",
    response_model=PruefzyklusRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_pruefzyklus(
    body: PruefzyklusCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Pruefzyklus:
    anlage = await session.get(Anlage, body.anlage_id)
    if anlage is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anlage nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )

    basis = body.letzte_pruefung_am or datetime.now(timezone.utc).date()
    pruefzyklus = Pruefzyklus(
        mandant_id=auth.mandant_id,
        anlage_id=body.anlage_id,
        bezeichnung=body.bezeichnung,
        intervall_monate=body.intervall_monate,
        letzte_pruefung_am=body.letzte_pruefung_am,
        naechste_pruefung_am=add_months(basis, body.intervall_monate),
    )
    session.add(pruefzyklus)
    await session.flush()
    await session.refresh(pruefzyklus)
    return pruefzyklus


@router.get("/{pruefzyklus_id}", response_model=PruefzyklusRead)
async def get_pruefzyklus(
    pruefzyklus_id: UUID, session: AsyncSession = Depends(get_db)
) -> Pruefzyklus:
    pruefzyklus = await session.get(Pruefzyklus, pruefzyklus_id)
    if pruefzyklus is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prüfzyklus nicht gefunden"
        )
    return pruefzyklus


@router.patch(
    "/{pruefzyklus_id}",
    response_model=PruefzyklusRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def update_pruefzyklus(
    pruefzyklus_id: UUID,
    body: PruefzyklusUpdate,
    session: AsyncSession = Depends(get_db),
) -> Pruefzyklus:
    pruefzyklus = await session.get(Pruefzyklus, pruefzyklus_id)
    if pruefzyklus is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prüfzyklus nicht gefunden"
        )

    changes = body.model_dump(exclude_unset=True)
    letzte_pruefung_explizit_gesetzt = "letzte_pruefung_am" in changes
    naechste_pruefung_explizit_gesetzt = "naechste_pruefung_am" in changes

    for field, value in changes.items():
        setattr(pruefzyklus, field, value)

    # Wird eine durchgefuehrte Pruefung eingetragen (oder das Intervall
    # geaendert), ohne dass die naechste Faelligkeit explizit mitgegeben
    # wurde, automatisch neu berechnen -- sonst muesste das Frontend diese
    # Rechnung dupliziert selbst machen.
    if letzte_pruefung_explizit_gesetzt and not naechste_pruefung_explizit_gesetzt:
        basis: date = pruefzyklus.letzte_pruefung_am or datetime.now(timezone.utc).date()
        pruefzyklus.naechste_pruefung_am = add_months(basis, pruefzyklus.intervall_monate)
        pruefzyklus.offener_vorgang_id = None

    await session.flush()
    await session.refresh(pruefzyklus)
    return pruefzyklus
