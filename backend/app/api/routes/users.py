from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.core.security import hash_password
from app.models.einladung import Einladung
from app.models.mandant import Mandant
from app.models.user import User
from app.schemas.einladung import EinladungRead, MitarbeiterEinladungCreate
from app.schemas.user import UserRead, UserUpdate
from app.services.audit_service import log_action
from app.services.einladung_service import create_einladung, to_read_model, versende_einladung

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get(
    "/einladungen",
    response_model=list[EinladungRead],
    dependencies=[Depends(require_roles("super_admin", "mandant_admin"))],
)
async def list_einladungen(session: AsyncSession = Depends(get_db)) -> list[EinladungRead]:
    result = await session.execute(
        select(Einladung).where(Einladung.art == "mitarbeiter").order_by(Einladung.created_at.desc())
    )
    return [EinladungRead(**to_read_model(e)) for e in result.scalars().all()]


@router.post(
    "/einladungen",
    response_model=EinladungRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("super_admin", "mandant_admin"))],
)
async def mitarbeiter_einladen(
    body: MitarbeiterEinladungCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> EinladungRead:
    if auth.role == "mandant_admin":
        if body.mandant_id is not None and body.mandant_id != auth.mandant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Einladungen können nur in den eigenen Mandanten verschickt werden",
            )
        ziel_mandant_id = auth.mandant_id
    else:
        if body.mandant_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="mandant_id ist erforderlich"
            )
        ziel_mandant_id = body.mandant_id

    mandant = await session.get(Mandant, ziel_mandant_id)
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mandant nicht gefunden")

    einladender = await session.get(User, auth.user_id)
    einladung = await create_einladung(
        session,
        mandant_id=ziel_mandant_id,
        email=body.email,
        art="mitarbeiter",
        rolle=body.role,
        eingeladen_von=auth.user_id,
    )
    link = await versende_einladung(
        session, einladung, absender_name=einladender.name if einladender else mandant.name
    )

    await log_action(
        session,
        aktion="mitarbeiter_eingeladen",
        mandant_id=ziel_mandant_id,
        actor_user_id=auth.user_id,
        entity_type="einladung",
        entity_id=einladung.id,
        payload={"email": einladung.email, "role": einladung.rolle},
    )
    return EinladungRead(**to_read_model(einladung, registrierungslink=link))


@router.post(
    "/einladungen/{einladung_id}/erneut-senden",
    response_model=EinladungRead,
    dependencies=[Depends(require_roles("super_admin", "mandant_admin"))],
)
async def einladung_erneut_senden(
    einladung_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> EinladungRead:
    einladung = await session.get(Einladung, einladung_id)
    if einladung is None or einladung.art != "mitarbeiter" or einladung.status != "offen":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Einladung nicht gefunden")

    einladender = await session.get(User, auth.user_id)
    mandant = await session.get(Mandant, einladung.mandant_id)
    link = await versende_einladung(
        session, einladung, absender_name=einladender.name if einladender else mandant.name
    )
    return EinladungRead(**to_read_model(einladung, registrierungslink=link))


@router.delete(
    "/einladungen/{einladung_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("super_admin", "mandant_admin"))],
)
async def einladung_widerrufen(
    einladung_id: UUID, session: AsyncSession = Depends(get_db)
) -> None:
    einladung = await session.get(Einladung, einladung_id)
    if einladung is None or einladung.art != "mitarbeiter" or einladung.status != "offen":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Einladung nicht gefunden")
    einladung.status = "widerrufen"
    await session.flush()


@router.get(
    "",
    response_model=list[UserRead],
    dependencies=[Depends(require_roles("super_admin", "mandant_admin", "disponent", "techniker"))],
)
async def list_users(session: AsyncSession = Depends(get_db)) -> list[User]:
    # RLS restricts a mandant_admin's session to their own mandant already;
    # super_admin sessions bypass RLS and therefore see every account.
    # Read-only for disponent/techniker too: colleagues' names are needed
    # for the @-mention picker in the Vorgangs-Chat (Phase 3) and aren't
    # sensitive the way account management (create/patch below) is.
    result = await session.execute(select(User).order_by(User.name))
    return list(result.scalars().all())


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    dependencies=[Depends(require_roles("super_admin", "mandant_admin"))],
)
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden"
        )

    if auth.role == "mandant_admin":
        if user.mandant_id != auth.mandant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden"
            )
        if body.role == "super_admin" or user.role == "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nicht berechtigt für super_admin-Accounts",
            )

    changes = body.model_dump(exclude_unset=True, exclude={"password"})
    for field, value in changes.items():
        setattr(user, field, value)
    if body.password:
        user.password_hash = hash_password(body.password)
        changes["password"] = "***"
    await session.flush()
    if changes:
        # See mandanten.update_mandant: UPDATE has no implicit RETURNING for
        # server-computed columns, so refresh before the response is built.
        await session.refresh(user)

    if changes:
        await log_action(
            session,
            aktion="user_geaendert",
            mandant_id=user.mandant_id,
            actor_user_id=auth.user_id,
            entity_type="user",
            entity_id=user.id,
            payload=changes,
        )
    return user


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("super_admin", "mandant_admin"))],
)
async def delete_user(
    user_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden")

    if auth.role == "mandant_admin":
        if user.mandant_id != auth.mandant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden")
        if user.role == "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nicht berechtigt für super_admin-Accounts",
            )

    if user.id == auth.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Der eigene Account kann nicht gelöscht werden"
        )

    if user.role == "mandant_admin":
        # Ein Mandant ohne jeden mandant_admin waere von niemandem mehr
        # verwaltbar -- der letzte muss also erhalten bleiben.
        andere_admins = await session.scalar(
            select(func.count()).select_from(User).where(
                User.mandant_id == user.mandant_id,
                User.role == "mandant_admin",
                User.id != user.id,
            )
        )
        if andere_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Der letzte Mandanten-Admin kann nicht gelöscht werden",
            )

    mandant_id = user.mandant_id
    audit_payload = {"email": user.email, "role": user.role}
    try:
        await session.delete(user)
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Nutzer kann nicht gelöscht werden, da noch Daten damit verknüpft sind "
                "(z.B. Zeiterfassungen, erstellte Angebote/Rechnungen) -- stattdessen deaktivieren."
            ),
        ) from exc

    await log_action(
        session,
        aktion="user_geloescht",
        mandant_id=mandant_id,
        actor_user_id=auth.user_id,
        entity_type="user",
        entity_id=user_id,
        payload=audit_payload,
    )
