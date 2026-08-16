import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import AuthContext, get_current_user
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
)
from app.db.session import system_session
from app.models.mandant import Mandant
from app.models.user import User
from app.schemas.auth import CurrentUser, LoginRequest, RefreshRequest, RegistrierenRequest, TokenPair
from app.services.auth_service import authenticate
from app.services.einladung_service import als_angenommen_markieren, resolve_offene_einladung

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest) -> TokenPair:
    return await authenticate(body.email, body.password)


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


@router.post("/registrieren", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def registrieren(body: RegistrierenRequest) -> TokenPair:
    """Schliesst eine Mitarbeiter-Einladung ab: legt den User-Account mit
    dem selbst gewaehlten Passwort an und loggt direkt ein."""
    if len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Passwort muss mindestens 8 Zeichen haben"
        )
    async with system_session() as session:
        einladung = await resolve_offene_einladung(session, body.token, erwartete_art="mitarbeiter")

        user = User(
            mandant_id=einladung.mandant_id,
            email=einladung.email,
            password_hash=hash_password(body.password),
            role=einladung.rolle,
            name=body.name,
        )
        session.add(user)
        await session.flush()
        await als_angenommen_markieren(session, einladung)

        return TokenPair(
            access_token=create_access_token(subject=user.id, role=user.role, mandant_id=user.mandant_id),
            refresh_token=create_refresh_token(subject=user.id, role=user.role, mandant_id=user.mandant_id),
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
