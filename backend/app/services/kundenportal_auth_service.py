from fastapi import HTTPException, status

from app.core.security import (
    create_kundenportal_access_token,
    create_kundenportal_refresh_token,
    verify_password,
)
from app.db.session import tenant_session
from app.models.mandant import Mandant
from app.schemas.auth import TokenPair
from app.services import system_lookups

_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="E-Mail oder Passwort falsch"
)


async def authenticate_kunde(email: str, password: str) -> TokenPair:
    """Mirrors app.services.auth_service.authenticate() for the separate
    Kundenportal identity space: email is unique platform-wide across
    kundenportal_zugaenge (not across users), so the tenant is not yet known
    at lookup time -- derselbe mandantenuebergreifende Lookup wie beim
    Staff-Login, danach nur noch unter der Mandanten-RLS."""
    zugang = await system_lookups.kundenzugang_by_email(email)

    if zugang is None or not verify_password(password, zugang.passwort_hash):
        raise _INVALID_CREDENTIALS
    if not zugang.aktiv:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Zugang ist deaktiviert"
        )

    async with tenant_session(mandant_id=zugang.mandant_id, is_super_admin=False) as session:
        mandant = await session.get(Mandant, zugang.mandant_id)
    if mandant is None or mandant.status != "aktiv":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Mandant ist nicht aktiv"
        )
    if "kundenportal" in mandant.deaktivierte_module:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kundenportal ist für diesen Betrieb nicht freigeschaltet",
        )

    return TokenPair(
        access_token=create_kundenportal_access_token(
            token_version=zugang.token_version,
            subject=zugang.id, mandant_id=zugang.mandant_id, kunde_id=zugang.kunde_id
        ),
        refresh_token=create_kundenportal_refresh_token(
            token_version=zugang.token_version,
            subject=zugang.id, mandant_id=zugang.mandant_id, kunde_id=zugang.kunde_id
        ),
    )
