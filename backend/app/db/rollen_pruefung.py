import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class UnsichereDbRolleError(RuntimeError):
    pass


async def pruefe_db_rolle(engine: AsyncEngine) -> None:
    """Superuser und BYPASSRLS-Rollen ignorieren jede RLS-Policy (auch mit
    FORCE ROW LEVEL SECURITY) -- die Mandantentrennung waere dann nur noch
    Anwendungslogik. Nur die App-/Worker-Verbindung wird geprueft;
    Migrationen laufen bewusst ueber dieselbe Rolle und brauchen keine
    Sonderrechte."""
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT current_user AS name, rolsuper, rolbypassrls "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            )
        ).one()

    if not (row.rolsuper or row.rolbypassrls):
        return

    meldung = (
        f"Datenbank-Rolle {row.name} ist Superuser/BYPASSRLS – Mandantentrennung "
        "per RLS wäre wirkungslos. Fix: scripts/app_rolle_einrichten.sh ausführen "
        "(siehe docs/DEPLOYMENT.md, Abschnitt 3)."
    )
    if get_settings().erlaube_rls_bypass_rolle:
        logger.warning(
            "%s FIELDVIBE_ERLAUBE_RLS_BYPASS_ROLLE ist gesetzt -- Start wird trotzdem "
            "fortgesetzt, die Mandantentrennung in der Datenbank ist AUSSER KRAFT.",
            meldung,
        )
        return
    raise UnsichereDbRolleError(
        meldung + " (Nur für Notfälle überschreibbar mit FIELDVIBE_ERLAUBE_RLS_BYPASS_ROLLE=1.)"
    )
