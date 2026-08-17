from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_recht, require_roles
from app.core.security import hash_password
from app.db.session import system_session
from app.models.account_typ import AccountTyp
from app.models.einladung import Einladung
from app.models.mandant import Mandant
from app.models.user import User
from app.schemas.einladung import EinladungRead, MitarbeiterEinladungCreate
from app.schemas.user import BottomNavUpdate, UserCreate, UserRead, UserUpdate
from app.services.audit_service import log_action
from app.services.einladung_service import create_einladung, to_read_model, versende_einladung

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


async def _to_read(session: AsyncSession, user: User) -> UserRead:
    account_typ = (
        await session.get(AccountTyp, user.account_typ_id)
        if user.account_typ_id is not None
        else None
    )
    return UserRead(
        id=user.id,
        mandant_id=user.mandant_id,
        email=user.email,
        role=user.role,
        account_typ_id=user.account_typ_id,
        account_typ_name=account_typ.name if account_typ is not None else None,
        nur_zugewiesene_kunden=account_typ.nur_zugewiesene_kunden if account_typ is not None else False,
        name=user.name,
        avatar_url=user.avatar_url,
        aktiv=user.aktiv,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


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

    if body.role == "custom":
        account_typ = await session.get(AccountTyp, body.account_typ_id)
        if account_typ is None or account_typ.mandant_id != ziel_mandant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account-Typ nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )

    einladender = await session.get(User, auth.user_id)
    einladung = await create_einladung(
        session,
        mandant_id=ziel_mandant_id,
        email=body.email,
        art="mitarbeiter",
        rolle=body.role,
        account_typ_id=body.account_typ_id,
        eingeladen_von=auth.user_id,
    )
    link = await versende_einladung(
        session,
        einladung,
        absender_name=einladender.name if einladender else mandant.name,
        absender_rolle=einladender.role if einladender else None,
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
        session,
        einladung,
        absender_name=einladender.name if einladender else mandant.name,
        absender_rolle=einladender.role if einladender else None,
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
    dependencies=[
        Depends(require_roles("super_admin", "mandant_admin", "custom")),
        Depends(require_recht("mitarbeiterverwaltung", "sehen")),
    ],
)
async def list_users(session: AsyncSession = Depends(get_db)) -> list[UserRead]:
    # RLS restricts a mandant_admin's session to their own mandant already;
    # super_admin sessions bypass RLS and therefore see every account.
    # Read-only for custom account types too: colleagues' names are needed
    # for the @-mention picker in the Vorgangs-Chat (Phase 3) and aren't
    # sensitive the way account management (create/patch below) is.
    result = await session.execute(select(User).order_by(User.name))
    users = list(result.scalars().all())

    account_typ_ids = {u.account_typ_id for u in users if u.account_typ_id is not None}
    account_typen: dict[UUID, AccountTyp] = {}
    if account_typ_ids:
        typen_result = await session.execute(
            select(AccountTyp).where(AccountTyp.id.in_(account_typ_ids))
        )
        account_typen = {t.id: t for t in typen_result.scalars().all()}

    return [
        UserRead(
            id=u.id,
            mandant_id=u.mandant_id,
            email=u.email,
            role=u.role,
            account_typ_id=u.account_typ_id,
            account_typ_name=account_typen[u.account_typ_id].name if u.account_typ_id in account_typen else None,
            nur_zugewiesene_kunden=account_typen[u.account_typ_id].nur_zugewiesene_kunden
            if u.account_typ_id in account_typen
            else False,
            name=u.name,
            avatar_url=u.avatar_url,
            aktiv=u.aktiv,
            created_at=u.created_at,
            updated_at=u.updated_at,
        )
        for u in users
    ]


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
) -> UserRead:
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

    if body.role == "custom":
        account_typ = await session.get(AccountTyp, body.account_typ_id)
        if account_typ is None or account_typ.mandant_id != body.mandant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account-Typ nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )

    user = User(
        mandant_id=body.mandant_id,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
        account_typ_id=body.account_typ_id if body.role == "custom" else None,
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
    return await _to_read(session, user)


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
) -> UserRead:
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
    if user.role == "custom":
        if user.account_typ_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="account_typ_id ist für role='custom' erforderlich",
            )
        account_typ = await session.get(AccountTyp, user.account_typ_id)
        if account_typ is None or account_typ.mandant_id != user.mandant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account-Typ nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
    else:
        user.account_typ_id = None
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
    return await _to_read(session, user)


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


@router.patch("/me/bottom-nav", response_model=BottomNavUpdate)
async def update_own_bottom_nav(
    body: BottomNavUpdate, auth: AuthContext = Depends(get_current_user)
) -> BottomNavUpdate:
    # Rein selbstbezogene Praeferenz -- jede Rolle darf sie fuer sich selbst
    # setzen, unabhaengig von mitarbeiterverwaltung-Rechten. Ueber
    # system_session() (analog auth.me), da die Route auch fuer
    # super_admin (mandant_id NULL, ausserhalb jeder RLS-Session) und
    # waehrend Impersonation greifen muss.
    async with system_session() as session:
        user = await session.get(User, auth.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden")
        # Immer vollstaendiger Ersatz beider Listen -- links/rotunde beide
        # None bedeutet "zur Standardauswahl zuruecksetzen" (siehe
        # BottomNavUpdate), sonst wird der komplette neue Stand gespeichert.
        user.bottom_nav_items = (
            None if body.links is None and body.rotunde is None else body.model_dump()
        )
        await session.flush()
    return body
