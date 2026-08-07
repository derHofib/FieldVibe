from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.account_typ import AccountTyp, AccountTypRecht
from app.models.user import User
from app.schemas.account_typ import (
    AccountTypCreate,
    AccountTypRead,
    AccountTypUpdate,
    RechteMatrixEintrag,
    RechtSetzen,
)
from app.services.rechte_service import rechte_matrix_fuer_account_typ

router = APIRouter(
    prefix="/api/account-typen",
    tags=["account-typen"],
    dependencies=[Depends(require_roles("mandant_admin"))],
)


async def _anzahl_nutzer(session: AsyncSession, account_typ_id: UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(User).where(User.account_typ_id == account_typ_id)
    )
    return result.scalar_one()


async def _to_read(session: AsyncSession, typ: AccountTyp) -> AccountTypRead:
    return AccountTypRead(
        id=typ.id,
        name=typ.name,
        icon=typ.icon,
        farbe=typ.farbe,
        nur_zugewiesene_kunden=typ.nur_zugewiesene_kunden,
        darf_vorgaenge_selbst_uebernehmen=typ.darf_vorgaenge_selbst_uebernehmen,
        reihenfolge=typ.reihenfolge,
        anzahl_nutzer=await _anzahl_nutzer(session, typ.id),
    )


@router.get("", response_model=list[AccountTypRead])
async def list_account_typen(
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[AccountTypRead]:
    result = await session.execute(
        select(AccountTyp)
        .where(AccountTyp.mandant_id == auth.mandant_id)
        .order_by(AccountTyp.reihenfolge, AccountTyp.name)
    )
    return [await _to_read(session, typ) for typ in result.scalars().all()]


@router.post("", response_model=AccountTypRead, status_code=status.HTTP_201_CREATED)
async def create_account_typ(
    body: AccountTypCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AccountTypRead:
    typ = AccountTyp(
        mandant_id=auth.mandant_id,
        name=body.name.strip(),
        icon=body.icon,
        farbe=body.farbe,
        nur_zugewiesene_kunden=body.nur_zugewiesene_kunden,
        darf_vorgaenge_selbst_uebernehmen=body.darf_vorgaenge_selbst_uebernehmen,
    )
    session.add(typ)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ein Account-Typ mit diesem Namen existiert bereits",
        ) from exc
    return await _to_read(session, typ)


@router.patch("/{account_typ_id}", response_model=AccountTypRead)
async def update_account_typ(
    account_typ_id: UUID,
    body: AccountTypUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AccountTypRead:
    typ = await session.get(AccountTyp, account_typ_id)
    if typ is None or typ.mandant_id != auth.mandant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account-Typ nicht gefunden")
    for feld, wert in body.model_dump(exclude_unset=True).items():
        setattr(typ, feld, wert.strip() if feld == "name" and isinstance(wert, str) else wert)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ein Account-Typ mit diesem Namen existiert bereits",
        ) from exc
    return await _to_read(session, typ)


@router.delete("/{account_typ_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account_typ(
    account_typ_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    typ = await session.get(AccountTyp, account_typ_id)
    if typ is None or typ.mandant_id != auth.mandant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account-Typ nicht gefunden")
    if await _anzahl_nutzer(session, account_typ_id) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Diesem Account-Typ sind noch Nutzer zugeordnet",
        )
    await session.execute(
        AccountTypRecht.__table__.delete().where(AccountTypRecht.account_typ_id == account_typ_id)
    )
    await session.delete(typ)
    await session.flush()


@router.get("/{account_typ_id}/rechte", response_model=list[RechteMatrixEintrag])
async def get_rechte(
    account_typ_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[RechteMatrixEintrag]:
    typ = await session.get(AccountTyp, account_typ_id)
    if typ is None or typ.mandant_id != auth.mandant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account-Typ nicht gefunden")
    matrix = await rechte_matrix_fuer_account_typ(session, account_typ_id)
    return [
        RechteMatrixEintrag(bereich=bereich, aktion=aktion, erlaubt=erlaubt)
        for bereich, aktionen in matrix.items()
        for aktion, erlaubt in aktionen.items()
    ]


@router.put("/{account_typ_id}/rechte", response_model=list[RechteMatrixEintrag])
async def set_recht(
    account_typ_id: UUID,
    body: RechtSetzen,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[RechteMatrixEintrag]:
    typ = await session.get(AccountTyp, account_typ_id)
    if typ is None or typ.mandant_id != auth.mandant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account-Typ nicht gefunden")
    result = await session.execute(
        select(AccountTypRecht).where(
            AccountTypRecht.account_typ_id == account_typ_id,
            AccountTypRecht.bereich == body.bereich,
            AccountTypRecht.aktion == body.aktion,
        )
    )
    eintrag = result.scalar_one_or_none()
    if eintrag is None:
        session.add(
            AccountTypRecht(
                account_typ_id=account_typ_id,
                bereich=body.bereich,
                aktion=body.aktion,
                erlaubt=body.erlaubt,
            )
        )
    else:
        eintrag.erlaubt = body.erlaubt
    await session.flush()

    matrix = await rechte_matrix_fuer_account_typ(session, account_typ_id)
    return [
        RechteMatrixEintrag(bereich=bereich, aktion=aktion, erlaubt=erlaubt)
        for bereich, aktionen in matrix.items()
        for aktion, erlaubt in aktionen.items()
    ]
