from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_recht, require_roles
from app.models.anlage import Anlage
from app.models.kunde import Kunde
from app.models.standort import Standort
from app.models.vorgang import Vorgang
from app.schemas.kunde import KundeRead
from app.schemas.profile import StandortProfil
from app.schemas.standort import StandortCreate, StandortRead, StandortUpdate
from app.services import papierkorb_service
from app.services.rechte_service import ist_auf_zugewiesene_kunden_beschraenkt
from app.services.zuweisung_service import assigned_kunde_ids

router = APIRouter(
    prefix="/api/standorte",
    tags=["standorte"],
    dependencies=[Depends(require_roles("mandant_admin", "custom", "loesch_operativ"))],
)


async def _require_own_kunde(session: AsyncSession, kunde_id: UUID) -> Kunde:
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kunde nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    return kunde


@router.get(
    "", response_model=list[StandortRead], dependencies=[Depends(require_recht("kunden", "sehen"))]
)
async def list_standorte(
    kunde_id: UUID | None = Query(default=None),
    aktiv: bool | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Standort]:
    stmt = select(Standort).where(Standort.geloescht_am.is_(None)).order_by(Standort.bezeichnung)
    if kunde_id:
        stmt = stmt.where(Standort.kunde_id == kunde_id)
    if aktiv is not None:
        stmt = stmt.where(Standort.aktiv == aktiv)
    if await ist_auf_zugewiesene_kunden_beschraenkt(
        session, role=auth.role, account_typ_id=auth.account_typ_id
    ):
        stmt = stmt.where(Standort.kunde_id.in_(await assigned_kunde_ids(session, auth.user_id)))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "",
    response_model=StandortRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("kunden", "erstellen")),
    ],
)
async def create_standort(
    body: StandortCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Standort:
    await _require_own_kunde(session, body.kunde_id)

    standort = Standort(
        mandant_id=auth.mandant_id,
        kunde_id=body.kunde_id,
        bezeichnung=body.bezeichnung,
        adresse=body.adresse,
        geo_lat=body.geo_lat,
        geo_lng=body.geo_lng,
    )
    session.add(standort)
    await session.flush()
    return standort


async def _require_standort_zugriff(session: AsyncSession, auth: AuthContext, standort: Standort) -> None:
    beschraenkt = await ist_auf_zugewiesene_kunden_beschraenkt(
        session, role=auth.role, account_typ_id=auth.account_typ_id
    )
    if beschraenkt and standort.kunde_id not in await assigned_kunde_ids(session, auth.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Standort nicht gefunden")


@router.get(
    "/{standort_id}",
    response_model=StandortRead,
    dependencies=[Depends(require_recht("kunden", "sehen"))],
)
async def get_standort(
    standort_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Standort:
    standort = await session.get(Standort, standort_id)
    if standort is None or standort.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Standort nicht gefunden")
    await _require_standort_zugriff(session, auth, standort)
    return standort


@router.get(
    "/{standort_id}/profil",
    response_model=StandortProfil,
    dependencies=[Depends(require_recht("kunden", "sehen"))],
)
async def get_standort_profil(
    standort_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> StandortProfil:
    standort = await session.get(Standort, standort_id)
    if standort is None or standort.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Standort nicht gefunden")
    await _require_standort_zugriff(session, auth, standort)
    kunde = await session.get(Kunde, standort.kunde_id)

    anlagen_result = await session.execute(
        select(Anlage)
        .where(Anlage.standort_id == standort_id, Anlage.geloescht_am.is_(None))
        .order_by(Anlage.bezeichnung)
    )
    vorgaenge_result = await session.execute(
        select(Vorgang)
        .where(Vorgang.standort_id == standort_id, Vorgang.geloescht_am.is_(None))
        .order_by(Vorgang.last_activity_at.desc())
        .limit(50)
    )
    status_result = await session.execute(
        select(Vorgang.status, func.count())
        .where(Vorgang.standort_id == standort_id)
        .group_by(Vorgang.status)
    )
    vorgaenge_nach_status = {status: count for status, count in status_result.all()}

    return StandortProfil(
        **StandortRead.model_validate(standort).model_dump(),
        kunde=KundeRead.model_validate(kunde) if kunde is not None else None,
        anlagen=list(anlagen_result.scalars().all()),
        vorgaenge=list(vorgaenge_result.scalars().all()),
        vorgaenge_nach_status=vorgaenge_nach_status,
    )


@router.patch(
    "/{standort_id}",
    response_model=StandortRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("kunden", "bearbeiten")),
    ],
)
async def update_standort(
    standort_id: UUID, body: StandortUpdate, session: AsyncSession = Depends(get_db)
) -> Standort:
    standort = await session.get(Standort, standort_id)
    if standort is None or standort.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Standort nicht gefunden")

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(standort, field, value)
    await session.flush()
    if changes:
        await session.refresh(standort)
    return standort


@router.delete(
    "/{standort_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("kunden", "loeschen")),
    ],
)
async def delete_standort(
    standort_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    # Papierkorb statt Hard-Delete: kaskadiert auf Anlagen und Vorgaenge
    # dieses Standorts (siehe app/services/papierkorb_service.py).
    standort = await papierkorb_service.soft_delete(
        session, entity_typ="standort", entity_id=standort_id, actor_user_id=auth.user_id
    )
    if standort is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Standort nicht gefunden")
