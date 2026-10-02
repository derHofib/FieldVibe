from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kundenportal import KundenportalZugang
from app.models.partner_zugang import PartnerZugang
from app.models.user import User


async def widerrufe_tokens(session: AsyncSession, account: User | KundenportalZugang | PartnerZugang) -> None:
    """Entwertet alle bisher ausgestellten Access-/Refresh-/Stream-Tokens des
    Accounts. Als SQL-Ausdruck statt Python-Addition, damit zwei gleichzeitige
    Widerrufe nicht denselben Wert schreiben."""
    modell = type(account)
    account.token_version = modell.token_version + 1
    await session.flush()
    await session.refresh(account, ["token_version"])
