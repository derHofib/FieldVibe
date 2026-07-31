from fastapi import HTTPException, status
from sqlalchemy import func, select

from app.core.security import (
    create_kundenportal_access_token,
    create_kundenportal_refresh_token,
    verify_password,
)
from app.db.session import system_session
from app.models.kundenportal import KundenportalZugang
from app.models.mandant import Mandant
from app.schemas.auth import TokenPair

_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="E-Mail oder Passwort falsch"
)


async def authenticate_kunde(email: str, password: str) -> TokenPair:
    """Mirrors app.services.auth_service.authenticate() for the separate
    Kundenportal identity space: email is unique platform-wide across
    kundenportal_zugaenge (not across users), so the tenant is not yet known
    at lookup time -- the same legitimate pre-authentication use of
    system_session() as the staff login."""
    async with system_session() as session:
        result = await session.execute(
            select(KundenportalZugang).where(
                func.lower(KundenportalZugang.email) == email.strip().lower()
            )
        )
        zugang = result.scalar_one_or_none()

        if zugang is None or not verify_password(password, zugang.password_hash):
            raise _INVALID_CREDENTIALS
        if not zugang.aktiv:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Zugang ist deaktiviert"
            )

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
                subject=zugang.id, mandant_id=zugang.mandant_id, kunde_id=zugang.kunde_id
            ),
            refresh_token=create_kundenportal_refresh_token(
                subject=zugang.id, mandant_id=zugang.mandant_id, kunde_id=zugang.kunde_id
            ),
        )
