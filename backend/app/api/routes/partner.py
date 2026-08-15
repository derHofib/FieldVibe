from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_module, require_roles
from app.core.security import hash_password
from app.models.partner import Partner
from app.models.partner_nachweis import PartnerNachweis
from app.models.partner_zugang import PartnerZugang
from app.schemas.partner import (
    PartnerCreate,
    PartnerNachweisCreate,
    PartnerNachweisRead,
    PartnerNachweisUpdate,
    PartnerRead,
    PartnerUpdate,
    PartnerZugangCreate,
    PartnerZugangRead,
    PartnerZugangUpdate,
)

router = APIRouter(
    prefix="/api/partner",
    tags=["partner"],
    dependencies=[Depends(require_module("nachunternehmer"))],
)


def _nachweis_to_read(nachweis: PartnerNachweis) -> PartnerNachweisRead:
    return PartnerNachweisRead(
        id=nachweis.id,
        partner_id=nachweis.partner_id,
        typ=nachweis.typ,
        gueltig_bis=nachweis.gueltig_bis,
        dokument_s3_key=nachweis.dokument_s3_key,
        notiz=nachweis.notiz,
        abgelaufen=nachweis.gueltig_bis is not None and nachweis.gueltig_bis < date.today(),
        created_at=nachweis.created_at,
        updated_at=nachweis.updated_at,
    )


@router.get(
    "",
    response_model=list[PartnerRead],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)
async def list_partner(session: AsyncSession = Depends(get_db)) -> list[Partner]:
    result = await session.execute(select(Partner).order_by(Partner.name))
    return list(result.scalars().all())


@router.post(
    "",
    response_model=PartnerRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_partner(
    body: PartnerCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Partner:
    partner = Partner(mandant_id=auth.mandant_id, **body.model_dump())
    session.add(partner)
    await session.flush()
    return partner


@router.get(
    "/{partner_id}",
    response_model=PartnerRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)
async def get_partner(partner_id: UUID, session: AsyncSession = Depends(get_db)) -> Partner:
    partner = await session.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner nicht gefunden")
    return partner


@router.patch(
    "/{partner_id}",
    response_model=PartnerRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def update_partner(
    partner_id: UUID, body: PartnerUpdate, session: AsyncSession = Depends(get_db)
) -> Partner:
    partner = await session.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner nicht gefunden")

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(partner, field, value)
    await session.flush()
    if changes:
        await session.refresh(partner)
    return partner


@router.delete(
    "/{partner_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def delete_partner(partner_id: UUID, session: AsyncSession = Depends(get_db)) -> None:
    partner = await session.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner nicht gefunden")

    # Nachweise/Zugaenge sind reine Anhaengsel (ondelete=CASCADE in der
    # Migration), Vorgaenge mit gesetztem partner_id blockieren die Loeschung
    # bewusst (kein ondelete auf vorgaenge.partner_id) -- exakt dasselbe
    # Restrict-Verhalten wie bei Kunde/Anlage (siehe kunden.py).
    try:
        await session.delete(partner)
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Partner kann nicht gelöscht werden, da noch Vorgänge zugewiesen sind -- stattdessen deaktivieren.",
        ) from exc


@router.get(
    "/{partner_id}/nachweise",
    response_model=list[PartnerNachweisRead],
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def list_nachweise(partner_id: UUID, session: AsyncSession = Depends(get_db)) -> list[PartnerNachweisRead]:
    if await session.get(Partner, partner_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner nicht gefunden")
    result = await session.execute(
        select(PartnerNachweis).where(PartnerNachweis.partner_id == partner_id).order_by(PartnerNachweis.typ)
    )
    return [_nachweis_to_read(n) for n in result.scalars().all()]


@router.post(
    "/{partner_id}/nachweise",
    response_model=PartnerNachweisRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_nachweis(
    partner_id: UUID,
    body: PartnerNachweisCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> PartnerNachweisRead:
    if await session.get(Partner, partner_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner nicht gefunden")
    nachweis = PartnerNachweis(mandant_id=auth.mandant_id, partner_id=partner_id, **body.model_dump())
    session.add(nachweis)
    await session.flush()
    return _nachweis_to_read(nachweis)


@router.patch(
    "/{partner_id}/nachweise/{nachweis_id}",
    response_model=PartnerNachweisRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def update_nachweis(
    partner_id: UUID,
    nachweis_id: UUID,
    body: PartnerNachweisUpdate,
    session: AsyncSession = Depends(get_db),
) -> PartnerNachweisRead:
    nachweis = await session.get(PartnerNachweis, nachweis_id)
    if nachweis is None or nachweis.partner_id != partner_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nachweis nicht gefunden")

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(nachweis, field, value)
    await session.flush()
    if changes:
        await session.refresh(nachweis)
    return _nachweis_to_read(nachweis)


@router.delete(
    "/{partner_id}/nachweise/{nachweis_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def delete_nachweis(
    partner_id: UUID, nachweis_id: UUID, session: AsyncSession = Depends(get_db)
) -> None:
    nachweis = await session.get(PartnerNachweis, nachweis_id)
    if nachweis is None or nachweis.partner_id != partner_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nachweis nicht gefunden")
    await session.delete(nachweis)
    await session.flush()


@router.get(
    "/{partner_id}/zugaenge",
    response_model=list[PartnerZugangRead],
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def list_zugaenge(partner_id: UUID, session: AsyncSession = Depends(get_db)) -> list[PartnerZugang]:
    if await session.get(Partner, partner_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner nicht gefunden")
    result = await session.execute(select(PartnerZugang).where(PartnerZugang.partner_id == partner_id))
    return list(result.scalars().all())


@router.post(
    "/{partner_id}/zugaenge",
    response_model=PartnerZugangRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_zugang(
    partner_id: UUID,
    body: PartnerZugangCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> PartnerZugang:
    if await session.get(Partner, partner_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner nicht gefunden")
    if len(body.password) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Passwort muss mindestens 10 Zeichen haben"
        )

    zugang = PartnerZugang(
        mandant_id=auth.mandant_id,
        partner_id=partner_id,
        email=body.email,
        password_hash=hash_password(body.password),
        name=body.name,
    )
    session.add(zugang)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="E-Mail wird bereits verwendet"
        ) from exc
    return zugang


@router.patch(
    "/{partner_id}/zugaenge/{zugang_id}",
    response_model=PartnerZugangRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def update_zugang(
    partner_id: UUID,
    zugang_id: UUID,
    body: PartnerZugangUpdate,
    session: AsyncSession = Depends(get_db),
) -> PartnerZugang:
    zugang = await session.get(PartnerZugang, zugang_id)
    if zugang is None or zugang.partner_id != partner_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zugang nicht gefunden")

    changes = body.model_dump(exclude_unset=True, exclude={"password"})
    for field, value in changes.items():
        setattr(zugang, field, value)
    if body.password is not None:
        if len(body.password) < 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwort muss mindestens 10 Zeichen haben",
            )
        zugang.password_hash = hash_password(body.password)
        changes["password_hash"] = zugang.password_hash

    await session.flush()
    if changes:
        await session.refresh(zugang)
    return zugang
