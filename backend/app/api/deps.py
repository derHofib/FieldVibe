from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import system_session, tenant_session
from app.models.mandant import Mandant
from app.services.rechte_service import hat_recht

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user_id: UUID
    mandant_id: UUID | None
    role: str
    impersonated_by: UUID | None = None
    account_typ_id: UUID | None = None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthContext:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Nicht authentifiziert"
        )
    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültiges Token"
        ) from exc

    if payload.get("type") not in ("access", "impersonation"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token-Typ nicht für API-Zugriff zulässig",
        )

    mandant_id = UUID(payload["mandant_id"]) if payload.get("mandant_id") else None
    impersonated_by = (
        UUID(payload["impersonated_by"]) if payload.get("impersonated_by") else None
    )
    account_typ_id = (
        UUID(payload["account_typ_id"]) if payload.get("account_typ_id") else None
    )
    return AuthContext(
        user_id=UUID(payload["sub"]),
        mandant_id=mandant_id,
        role=payload["role"],
        impersonated_by=impersonated_by,
        account_typ_id=account_typ_id,
    )


async def get_db(
    auth: AuthContext = Depends(get_current_user),
) -> AsyncIterator[AsyncSession]:
    """Tenant-scoped DB session. super_admin gets an RLS-bypassing session
    reserved for cross-tenant platform administration; every other role is
    hard-pinned to its own mandant_id via Row Level Security."""
    is_super_admin = auth.role == "super_admin"
    ctx = (
        system_session()
        if is_super_admin
        else tenant_session(mandant_id=auth.mandant_id, is_super_admin=False)
    )
    async with ctx as session:
        yield session


def require_roles(*roles: str):
    async def checker(auth: AuthContext = Depends(get_current_user)) -> AuthContext:
        # loesch_operativ (Papierkorb, siehe app/api/routes/papierkorb.py) hat
        # zusaetzlich zum Loeschen/Wiederherstellen/endgueltigen Loeschen
        # dieselben Rechte wie ein mandant_admin -- ueberall im Code, wo
        # mandant_admin erlaubt ist, ist loesch_operativ es damit implizit
        # auch, ohne dass jede einzelne require_roles(...)-Stelle angepasst
        # werden muesste. Einzige Ausnahme: die super_admin-only vergebbaren
        # Papierkorb-Rollen selbst duerfen auch von loesch_operativ nicht
        # vergeben werden (siehe app/api/routes/users.py).
        if auth.role == "loesch_operativ" and "mandant_admin" in roles:
            return auth
        if auth.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Keine Berechtigung für diese Aktion",
            )
        return auth

    return checker


def require_module(*modules: str):
    """Sperrt einen Endpunkt, wenn der Mandant ALLE uebergebenen Module
    deaktiviert hat (Mehrfachangabe = "erlaubt, wenn mindestens eines davon
    aktiv ist" -- fuer Anlagen, die sowohl zu 'kundenverwaltung' als auch zu
    'material' gehoeren koennen). super_admin (mandant_id is None, ausser bei
    Impersonation) ist von der Pruefung ausgenommen -- Modul-Flags sind ein
    mandantenbezogenes Konzept, keine Plattform-Einschraenkung."""

    async def checker(
        auth: AuthContext = Depends(get_current_user),
        session: AsyncSession = Depends(get_db),
    ) -> AuthContext:
        if auth.mandant_id is None:
            return auth
        mandant = await session.get(Mandant, auth.mandant_id)
        if mandant is not None and set(mandant.deaktivierte_module).issuperset(modules):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Diese Funktion ist für Ihren Account nicht freigeschaltet",
            )
        return auth

    return checker


def require_recht(bereich: str, aktion: str = "sehen"):
    """Zusaetzlich zu require_roles: schraenkt frei vom mandant_admin
    definierte Account-Typen (role == 'custom', siehe app/models/account_typ.py)
    gemaess ihrer individuellen Rechte-Matrix ein (siehe
    app/services/rechte_service.py). super_admin/mandant_admin sind hier immer
    erlaubt -- deren Zugriff wird ausschliesslich ueber require_roles an der
    jeweiligen Route gesteuert und bleibt von dieser Matrix unberuehrt."""

    async def checker(
        auth: AuthContext = Depends(get_current_user),
        session: AsyncSession = Depends(get_db),
    ) -> AuthContext:
        if auth.role != "custom":
            return auth
        erlaubt = await hat_recht(
            session, account_typ_id=auth.account_typ_id, bereich=bereich, aktion=aktion
        )
        if not erlaubt:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Keine Berechtigung für diese Aktion",
            )
        return auth

    return checker


@dataclass(frozen=True)
class KundenAuthContext:
    zugang_id: UUID
    mandant_id: UUID
    kunde_id: UUID


async def get_current_kunde(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> KundenAuthContext:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Nicht authentifiziert"
        )
    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültiges Token"
        ) from exc

    if payload.get("type") != "kundenportal_access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token-Typ nicht für das Kundenportal zulässig",
        )

    return KundenAuthContext(
        zugang_id=UUID(payload["sub"]),
        mandant_id=UUID(payload["mandant_id"]),
        kunde_id=UUID(payload["kunde_id"]),
    )


async def get_kunden_db(
    auth: KundenAuthContext = Depends(get_current_kunde),
) -> AsyncIterator[AsyncSession]:
    """Tenant-scoped session for the Kundenportal.

    RLS here only enforces the mandant boundary (same as any tenant_session)
    -- it has no concept of "this row belongs to this one Kunde". Every
    Kundenportal route MUST additionally filter its queries by
    `auth.kunde_id` explicitly; this session alone does not prevent one
    customer from reading another customer's data within the same mandant.
    """
    async with tenant_session(mandant_id=auth.mandant_id, is_super_admin=False) as session:
        yield session


def require_module_kunde(*modules: str):
    """Kundenportal-Pendant zu require_module: greift schon vorm Login (siehe
    kundenportal_auth_service.authenticate_kunde), dieser Checker deckt die
    Datenroutern ab, die bereits ein gueltiges Kundenportal-Token voraussetzen."""

    async def checker(
        auth: KundenAuthContext = Depends(get_current_kunde),
        session: AsyncSession = Depends(get_kunden_db),
    ) -> KundenAuthContext:
        mandant = await session.get(Mandant, auth.mandant_id)
        if mandant is not None and set(mandant.deaktivierte_module).issuperset(modules):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Diese Funktion ist für Ihren Account nicht freigeschaltet",
            )
        return auth

    return checker
