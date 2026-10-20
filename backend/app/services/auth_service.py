from fastapi import HTTPException, status
from sqlalchemy import func, select

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_user_mfa_token,
    verify_password,
)
from app.db.session import system_session
from app.models.mandant import Mandant
from app.models.user import User
from app.schemas.auth import LoginResponse, TokenPair
from app.services import mfa_service

_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="E-Mail oder Passwort falsch"
)


async def token_paar_fuer(session: AsyncSession, user: User, mandant: Mandant | None = None) -> TokenPair:
    """Einziger Ausstellungsort fuer Mitarbeiter-Token-Paare. Der Zugriffstoken
    bekommt das Einrichtungs-Kennzeichen, solange der Mandant MFA verlangt und
    der Account keine hat -- bei jedem Refresh neu bewertet, damit eine
    nachtraeglich eingeschaltete Pflicht spaetestens dann greift."""
    if mandant is None and user.mandant_id is not None:
        mandant = await session.get(Mandant, user.mandant_id)
    return TokenPair(
        access_token=create_access_token(
            token_version=user.token_version,
            subject=user.id,
            role=user.role,
            mandant_id=user.mandant_id,
            account_typ_id=user.account_typ_id,
            mfa_einrichtung=mfa_service.einrichtung_erforderlich(user, mandant),
        ),
        refresh_token=create_refresh_token(
            token_version=user.token_version,
            subject=user.id,
            role=user.role,
            mandant_id=user.mandant_id,
            account_typ_id=user.account_typ_id,
        ),
    )


async def authenticate(email: str, password: str) -> LoginResponse:
    """Looks up the user by email across all tenants.

    This is the one legitimate pre-authentication use of system_session():
    email is unique platform-wide, so at this point in the request we do not
    yet know -- and cannot know -- which tenant to scope to. The lookup
    itself never returns tenant data to the caller, only a token for the
    single matched account.
    """
    async with system_session() as session:
        # func.lower() auf beiden Seiten statt eines vorab normalisierten
        # `email`-Arguments zu vertrauen -- so bleibt der Login auch dann
        # case-insensitiv, wenn ein Aufrufer (Seed-Skript, direkter
        # DB-Insert) die App-seitige Normalisierung beim Anlegen umgangen hat.
        result = await session.execute(
            select(User).where(func.lower(User.email) == email.strip().lower())
        )
        user = result.scalar_one_or_none()

        if user is None or not verify_password(password, user.password_hash):
            raise _INVALID_CREDENTIALS

        if not user.aktiv:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Account ist deaktiviert"
            )

        mandant = None
        if user.mandant_id is not None:
            mandant_result = await session.execute(
                select(Mandant).where(Mandant.id == user.mandant_id)
            )
            mandant = mandant_result.scalar_one_or_none()
            if mandant is None or mandant.status != "aktiv":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Mandant ist nicht aktiv",
                )

        if user.mfa_aktiv:
            return LoginResponse(
                mfa_erforderlich=True,
                mfa_token=create_user_mfa_token(user_id=user.id, token_version=user.token_version),
            )
        paar = await token_paar_fuer(session, user, mandant)
        return LoginResponse(access_token=paar.access_token, refresh_token=paar.refresh_token)
