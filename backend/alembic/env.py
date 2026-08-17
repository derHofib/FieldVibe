from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.core.config import get_settings
from app.db.base import Base
from app.models import *  # noqa: F401,F403  (registers models on Base.metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Binding this here means Base.metadata.naming_convention (app/db/base.py)
# is also active during migrations, not just for autogenerate diffing.
# Gotcha discovered/fixed in 0022_check_constraint_namen_fix.py: inside a
# migration, sa.CheckConstraint(cond, name="ck_x_y") passed straight to
# op.create_table()/op.add_constraint() gets the "ck" convention applied to
# it a SECOND time (its given name is treated as the raw constraint_name
# token), silently producing "ck_x_ck_x_y" instead of "ck_x_y". Wrap any new
# migration's literal constraint name in op.f("ck_x_y") to mark it as
# already-final and skip that re-application.
target_metadata = Base.metadata

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url_sync)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Migrationen laufen ueber die normale App-DB-Rolle (kein
        # Postgres-Superuser, siehe 0-Downtime-Deployment/NOSUPERUSER-
        # Haertung), die denselben Row-Level-Security-Policies unterliegt
        # wie jede App-Session. Ohne Bypass sieht ein Backfill-UPDATE nur
        # Zeilen des (hier gar nicht gesetzten) app.current_mandant und
        # laesst andere Mandanten unveraendert -- ein nachfolgendes
        # ALTER COLUMN ... SET NOT NULL prueft aber alle Zeilen und
        # schlaegt dann mit NotNullViolation fehl (siehe 0023, wo genau
        # das bei bestehenden Mandantendaten passiert ist).
        connection.execute(text("SET app.is_super_admin = 'true'"))
        # SQLAlchemy 2.0 "autobegin" hat durch das obige execute() bereits
        # eine Transaktion auf der Connection eroeffnet. Ohne diesen Commit
        # haengt sich context.begin_transaction() unten in eben diese schon
        # laufende Transaktion ein, deren Ende (Connection-Close ohne
        # explizites commit()) SQLAlchemy 2.0 als Rollback behandelt -- die
        # Migration liefe dann scheinbar fehlerfrei durch (kein Traceback,
        # exit code 0), aber jede DDL/DML dieser Migration waere beim
        # Verbindungsende wieder verworfen. Der Commit hier schliesst die
        # SET-Transaktion sauber ab, damit die eigentliche Migration in
        # einer frischen, von alembic selbst verwalteten Transaktion laeuft.
        connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
