from fastapi import HTTPException, status
from sqlalchemy import func, select

from app.core.security import (
    create_partner_access_token,
    create_partner_refresh_token,
    verify_password,
)
from app.db.session import system_session
from app.models.mandant import Mandant
from app.models.partner_zugang import PartnerZugang
from app.schemas.auth import TokenPair

_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="E-Mail oder Passwort falsch"
)


async def authenticate_partner(email: str, password: str) -> TokenPair:
    """Mirrors app.services.kundenportal_auth_service.authenticate_kunde()
    fuer den Partner-Identitaetsraum: email ist plattformweit eindeutig
    ueber partner_zugaenge (nicht ueber users/kundenportal_zugaenge), der
    Mandant ist beim Lookup also noch nicht bekannt -- dieselbe legitime
    Pre-Auth-Nutzung von system_session() wie beim Staff- und
    Kundenportal-Login."""
    async with system_session() as session:
        result = await session.execute(
            select(PartnerZugang).where(
                func.lower(PartnerZugang.email) == email.strip().lower()
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
        if "nachunternehmer" in mandant.deaktivierte_module:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Partnerportal ist für diesen Betrieb nicht freigeschaltet",
            )

        return TokenPair(
            access_token=create_partner_access_token(
                subject=zugang.id, mandant_id=zugang.mandant_id, partner_id=zugang.partner_id
            ),
            refresh_token=create_partner_refresh_token(
                subject=zugang.id, mandant_id=zugang.mandant_id, partner_id=zugang.partner_id
            ),
        )
