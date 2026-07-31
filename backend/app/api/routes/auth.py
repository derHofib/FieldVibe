import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
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
from app.models.mandant import Mandant
from app.models.user import User
from app.schemas.auth import CurrentUser, LoginRequest, RefreshRequest, TokenPair
from app.services.auth_service import authenticate

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
                subject=user.id, role=user.role, mandant_id=user.mandant_id
            ),
            refresh_token=create_refresh_token(
                subject=user.id, role=user.role, mandant_id=user.mandant_id
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

        return CurrentUser(
            id=user.id,
            mandant_id=auth.mandant_id,
            role=auth.role,
            name=user.name,
            email=user.email,
            impersonated_by=auth.impersonated_by,
            mandant_name=mandant_name,
            deaktivierte_module=deaktivierte_module,
        )
