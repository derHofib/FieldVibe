from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_module, require_roles
from app.models.anlage import Anlage
from app.models.inventurzyklus import InventurZyklus
from app.schemas.inventurzyklus import InventurZyklusCreate, InventurZyklusRead, InventurZyklusUpdate
from app.services import papierkorb_service

# loesch_operativ ist hier die einzige Abweichung von der sonst techniker-
# aehnlichen Sichtbarkeit dieses Routers -- es braucht Zugriff, um
# Inventurzyklen loeschen/wiederherstellen zu koennen (siehe papierkorb.py).
router = APIRouter(
    prefix="/api/inventurzyklen",
    tags=["inventurzyklen"],
    dependencies=[
        Depends(require_roles("mandant_admin", "disponent", "techniker", "loesch_operativ")),
        Depends(require_module("fahrzeuge")),
    ],
)

LAGERORT_OBJEKTTYPEN = ("fahrzeug", "lager", "baustelle")


async def _require_lagerort(session: AsyncSession, lager_id: UUID) -> Anlage:
    lager = await session.get(Anlage, lager_id)
    if lager is None or lager.objekttyp not in LAGERORT_OBJEKTTYPEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Lagerort nicht gefunden"
        )
    return lager


@router.get("", response_model=list[InventurZyklusRead])
async def list_inventurzyklen(
    lager_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> list[InventurZyklus]:
    stmt = (
        select(InventurZyklus)
        .where(InventurZyklus.geloescht_am.is_(None))
        .order_by(InventurZyklus.naechste_inventur_am.asc())
    )
    if lager_id:
        stmt = stmt.where(InventurZyklus.lager_id == lager_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "",
    response_model=InventurZyklusRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_inventurzyklus(
    body: InventurZyklusCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> InventurZyklus:
    await _require_lagerort(session, body.lager_id)

    bestehender = (
        await session.execute(
            select(InventurZyklus).where(
                InventurZyklus.lager_id == body.lager_id,
                InventurZyklus.geloescht_am.is_(None),
            )
        )
    ).scalar_one_or_none()
    if bestehender is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Für diesen Lagerort existiert bereits ein Inventurzyklus",
        )

    zyklus = InventurZyklus(
        mandant_id=auth.mandant_id,
        lager_id=body.lager_id,
        intervall_tage=body.intervall_tage,
        naechste_inventur_am=body.naechste_inventur_am
        or (date.today() + timedelta(days=body.intervall_tage)),
    )
    session.add(zyklus)
    await session.flush()
    await session.refresh(zyklus)
    return zyklus


@router.get("/{inventurzyklus_id}", response_model=InventurZyklusRead)
async def get_inventurzyklus(
    inventurzyklus_id: UUID, session: AsyncSession = Depends(get_db)
) -> InventurZyklus:
    zyklus = await session.get(InventurZyklus, inventurzyklus_id)
    if zyklus is None or zyklus.geloescht_am is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Inventurzyklus nicht gefunden"
        )
    return zyklus


@router.delete(
    "/{inventurzyklus_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "loesch_operativ"))],
)
async def delete_inventurzyklus(
    inventurzyklus_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    zyklus = await papierkorb_service.soft_delete(
        session, entity_typ="inventurzyklus", entity_id=inventurzyklus_id, actor_user_id=auth.user_id
    )
    if zyklus is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Inventurzyklus nicht gefunden"
        )


@router.patch(
    "/{inventurzyklus_id}",
    response_model=InventurZyklusRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def update_inventurzyklus(
    inventurzyklus_id: UUID,
    body: InventurZyklusUpdate,
    session: AsyncSession = Depends(get_db),
) -> InventurZyklus:
    zyklus = await session.get(InventurZyklus, inventurzyklus_id)
    if zyklus is None or zyklus.geloescht_am is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Inventurzyklus nicht gefunden"
        )

    changes = body.model_dump(exclude_unset=True)
    letzte_explizit_gesetzt = "letzte_inventur_am" in changes
    naechste_explizit_gesetzt = "naechste_inventur_am" in changes

    for field, value in changes.items():
        setattr(zyklus, field, value)

    # Wird eine durchgefuehrte Inventur eingetragen (oder das Intervall
    # geaendert), ohne dass die naechste Faelligkeit explizit mitgegeben
    # wurde, automatisch neu berechnen -- analog zu Pruefzyklus.
    if letzte_explizit_gesetzt and not naechste_explizit_gesetzt:
        basis = zyklus.letzte_inventur_am or date.today()
        zyklus.naechste_inventur_am = basis + timedelta(days=zyklus.intervall_tage)

    await session.flush()
    await session.refresh(zyklus)
    return zyklus
