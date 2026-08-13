import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy import select

from app.api.deps import AuthContext, get_current_user
from app.core.rate_limit import client_ip, login_account_limiter, login_ip_limiter
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.db.session import system_session
from app.models.account_typ import RECHTE_AKTIONEN, RECHTE_BEREICHE, AccountTyp
from app.models.mandant import Mandant
from app.models.user import User
from app.schemas.auth import CurrentUser, LoginRequest, RefreshRequest, TokenPair
from app.schemas.user import BottomNavUpdate
from app.services.auth_service import authenticate
from app.services.rechte_service import darf_vorgang_selbst_uebernehmen, rechte_matrix_fuer_account_typ

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, request: Request) -> TokenPair:
    ip_key = client_ip(request)
    account_key = body.email.strip().lower()
    login_ip_limiter.check(ip_key)
    login_account_limiter.check(account_key)
    try:
        result = await authenticate(body.email, body.password)
    except HTTPException:
        login_ip_limiter.record_failure(ip_key)
        login_account_limiter.record_failure(account_key)
        raise
    login_ip_limiter.record_success(ip_key)
    login_account_limiter.record_success(account_key)
    return result


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest) -> TokenPair:
    try:
        payload = decode_token(body.refresh_token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültiges Refresh-Token"
        ) from exc

    if payload.get("type") != TokenType.REFRESH.value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Kein Refresh-Token"
        )

    async with system_session() as session:
        result = await session.execute(select(User).where(User.id == payload["sub"]))
        user = result.scalar_one_or_none()
        if user is None or not user.aktiv:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Account nicht gültig"
            )

        return TokenPair(
            access_token=create_access_token(
                subject=user.id,
                role=user.role,
                mandant_id=user.mandant_id,
                account_typ_id=user.account_typ_id,
            ),
            refresh_token=create_refresh_token(
                subject=user.id,
                role=user.role,
                mandant_id=user.mandant_id,
                account_typ_id=user.account_typ_id,
            ),
        )


@router.get("/me", response_model=CurrentUser)
async def me(auth: AuthContext = Depends(get_current_user)) -> CurrentUser:
    # Looked up via system_session deliberately: during impersonation the
    # token's `sub` is the real super_admin's user id, whose own row has
    # mandant_id = NULL and would be invisible under the impersonated
    # tenant's RLS scope. This lookup is read-only, keyed by the token's own
    # verified subject, and never returns another account's data.
    async with system_session() as session:
        result = await session.execute(select(User).where(User.id == auth.user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden"
            )

        mandant_name: str | None = None
        deaktivierte_module: list[str] = []
        if auth.mandant_id is not None:
            mandant = await session.get(Mandant, auth.mandant_id)
            if mandant is not None:
                mandant_name = mandant.name
                deaktivierte_module = mandant.deaktivierte_module

        account_typ_name: str | None = None
        nur_zugewiesene_kunden = False
        if auth.account_typ_id is not None:
            account_typ = await session.get(AccountTyp, auth.account_typ_id)
            if account_typ is not None:
                account_typ_name = account_typ.name
                nur_zugewiesene_kunden = account_typ.nur_zugewiesene_kunden

        selbst_uebernehmen = await darf_vorgang_selbst_uebernehmen(
            session, role=auth.role, account_typ_id=auth.account_typ_id
        )

        if auth.role == "custom" and auth.account_typ_id is not None:
            matrix = await rechte_matrix_fuer_account_typ(session, auth.account_typ_id)
            rechte = {
                bereich: [aktion for aktion, erlaubt in aktionen.items() if erlaubt]
                for bereich, aktionen in matrix.items()
            }
        else:
            # mandant_admin/super_admin/loesch_* kommen an require_recht()
            # ohnehin immer vorbei (siehe app/api/deps.py) -- die Matrix
            # spiegelt das 1:1, damit das Frontend nicht zusaetzlich nach
            # der Rolle unterscheiden muss.
            rechte = {bereich: list(RECHTE_AKTIONEN) for bereich in RECHTE_BEREICHE}

        # Defensiv statt user.bottom_nav_items direkt durchzureichen: falls
        # dort noch ein Wert aus der frueheren, flachen Listen-Form steckt
        # (vor der Aufteilung in links/rotunde), wuerde die Validierung sonst
        # fehlschlagen und /me fuer diesen Nutzer komplett blockieren --
        # stattdessen faellt das Frontend dann einfach auf die Standardauswahl
        # zurueck, statt den Login zu verhindern.
        bottom_nav_items: BottomNavUpdate | None = None
        if isinstance(user.bottom_nav_items, dict):
            try:
                bottom_nav_items = BottomNavUpdate.model_validate(user.bottom_nav_items)
            except ValidationError:
                bottom_nav_items = None

        return CurrentUser(
            id=user.id,
            mandant_id=auth.mandant_id,
            role=auth.role,
            account_typ_id=auth.account_typ_id,
            account_typ_name=account_typ_name,
            nur_zugewiesene_kunden=nur_zugewiesene_kunden,
            darf_vorgaenge_selbst_uebernehmen=selbst_uebernehmen,
            name=user.name,
            email=user.email,
            impersonated_by=auth.impersonated_by,
            mandant_name=mandant_name,
            deaktivierte_module=deaktivierte_module,
            bottom_nav_items=bottom_nav_items,
            rechte=rechte,
        )
