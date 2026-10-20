import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class UnsichereDbRolleError(RuntimeError):
    pass


# Rolle darf die Tabelle per ALTER TABLE aendern (Eigentuemer bzw. Mitglied der
# Eigentuemer-Rolle). pg_has_role(.., 'USAGE') bildet genau diese Postgres-
# Eigentumspruefung ab. Eine Parameter-Rolle statt current_user, damit der Test
# die Abfrage gegen eine Rolle ohne Besitz laufen lassen kann.
_BESITZ_SQL = text(
    "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND c.relrowsecurity "
    "AND pg_has_role(:rolle, c.relowner, 'USAGE') ORDER BY c.relname"
)


async def rls_tabellen_im_besitz(conn, rolle: str | None = None) -> list[str]:
    if rolle is None:
        rolle = (await conn.execute(text("SELECT current_user"))).scalar_one()
    return [r[0] for r in (await conn.execute(_BESITZ_SQL, {"rolle": rolle})).all()]


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
        await _pruefe_besitz(engine, row.name)
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


async def _pruefe_besitz(engine: AsyncEngine, rolle: str) -> None:
    """Eine Rolle, der die RLS-Tabellen gehoeren, kann RLS per ALTER TABLE ...
    DISABLE ROW LEVEL SECURITY / NO FORCE selbst abschalten -- ein SQL-Injection-
    Treffer reichte dann, die Mandantentrennung auszuhebeln. Standardmaessig nur
    eine Warnung, weil die Migrationen bisher ueber dieselbe Rolle laufen; mit
    FIELDVIBE_DB_BESITZ_VERBOTEN=1 bricht der Start ab (getrennte Owner-Rolle,
    siehe docs/DEPLOYMENT.md, Abschnitt Sicherheit)."""
    async with engine.connect() as conn:
        tabellen = await rls_tabellen_im_besitz(conn, rolle)
    if not tabellen:
        return
    meldung = (
        f"Datenbank-Rolle {rolle} besitzt {len(tabellen)} RLS-Tabellen und koennte die "
        "Row-Level-Security selbst abschalten. Abhilfe: getrennte Owner-Rolle fuer "
        "Migrationen (scripts/app_rolle_einrichten.sh --getrennter-owner)."
    )
    if get_settings().db_besitz_verboten:
        raise UnsichereDbRolleError(meldung)
    logger.warning(meldung)
