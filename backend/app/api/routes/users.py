from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_recht, require_roles
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/users", tags=["users"])

# Siehe app/services/papierkorb_service.py: nur super_admin darf diese
# Rollen vergeben/entziehen -- weder ein mandant_admin noch ein
# loesch_operativ (das via app/api/deps.py:require_roles() ansonsten
# ueberall dieselben Rechte wie mandant_admin hat) sollen sich diese
# Berechtigung selbst zuweisen bzw. sie weiterreichen koennen.
_PAPIERKORB_ROLLEN = ("loesch_ansicht", "loesch_operativ")


def _integrity_error_detail(exc: IntegrityError) -> str:
    constraint = getattr(getattr(exc, "orig", None), "constraint_name", None)
    if constraint == "uq_users_mandant_loesch_operativ_aktiv":
        return "Für diesen Mandanten existiert bereits ein aktiver loesch_operativ-Account"
    return "E-Mail bereits vergeben"


@router.get(
    "",
    response_model=list[UserRead],
    dependencies=[
        Depends(
            require_roles(
                "super_admin",
                "mandant_admin",
                "disponent",
                "techniker",
                "controller",
                "mitarbeiter",
            )
        ),
        Depends(require_recht("mitarbeiterverwaltung", "sehen")),
    ],
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
    if auth.role in ("mandant_admin", "loesch_operativ"):
        if body.role == "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="mandant_admin darf keine super_admin-Accounts anlegen",
            )
        # Papierkorb-Rollen (siehe app/services/papierkorb_service.py) sind
        # bewusst nur durch super_admin vergebbar -- loesch_operativ sieht
        # fachliche Daten wie ein mitarbeiter UND darf zusaetzlich loeschen/
        # wiederherstellen, ein mandant_admin soll sich diese Berechtigung
        # nicht selbst zuweisen koennen.
        if body.role in _PAPIERKORB_ROLLEN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="mandant_admin darf keine Papierkorb-Accounts anlegen",
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
            status_code=status.HTTP_409_CONFLICT, detail=_integrity_error_detail(exc)
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

    if auth.role in ("mandant_admin", "loesch_operativ"):
        if user.mandant_id != auth.mandant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden"
            )
        if body.role == "super_admin" or user.role == "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nicht berechtigt für super_admin-Accounts",
            )
        if body.role in _PAPIERKORB_ROLLEN or user.role in _PAPIERKORB_ROLLEN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nicht berechtigt für Papierkorb-Accounts",
            )

    changes = body.model_dump(exclude_unset=True, exclude={"password"})
    for field, value in changes.items():
        setattr(user, field, value)
    if body.password:
        user.password_hash = hash_password(body.password)
        changes["password"] = "***"
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=_integrity_error_detail(exc)
        ) from exc
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

    if auth.role in ("mandant_admin", "loesch_operativ"):
        if user.mandant_id != auth.mandant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden")
        if user.role == "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nicht berechtigt für super_admin-Accounts",
            )
        if user.role in _PAPIERKORB_ROLLEN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nicht berechtigt für Papierkorb-Accounts",
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
