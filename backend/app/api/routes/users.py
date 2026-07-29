from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/users", tags=["users"])


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


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("super_admin", "mandant_admin"))],
)
async def create_user(
    body: UserCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> User:
    if auth.role == "mandant_admin":
        if body.role == "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="mandant_admin darf keine super_admin-Accounts anlegen",
            )
        if body.mandant_id != auth.mandant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accounts können nur im eigenen Mandanten angelegt werden",
            )

    user = User(
        mandant_id=body.mandant_id,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
        name=body.name,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="E-Mail bereits vergeben"
        ) from exc

    await log_action(
        session,
        aktion="user_erstellt",
        mandant_id=user.mandant_id,
        actor_user_id=auth.user_id,
        entity_type="user",
        entity_id=user.id,
        payload={"email": user.email, "role": user.role},
    )
    return user


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
