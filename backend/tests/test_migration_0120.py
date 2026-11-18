"""Migration 0120 (erstellt_via an form_schemas/form_submissions): up/down/up, Check-Constraint, kein Backfill."""
import asyncio
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from tests.conftest import sync_system_engine

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TABELLEN = ("form_schemas", "form_submissions")


def _cfg() -> Config:
    cfg = Config(os.path.join(_BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND, "alembic"))
    return cfg


async def _migrieren(richtung: str, ziel: str) -> None:
    await asyncio.to_thread(getattr(command, richtung), _cfg(), ziel)


@pytest.mark.asyncio
async def test_migration_0120_up_down_up():
    engine = sync_system_engine()
    try:
        await _migrieren("downgrade", "0119")
        with engine.connect() as conn:
            for tabelle in _TABELLEN:
                assert "erstellt_via" not in {c["name"] for c in inspect(conn).get_columns(tabelle)}

        await _migrieren("upgrade", "0120")
        with engine.connect() as conn:
            for tabelle in _TABELLEN:
                spalte = next(c for c in inspect(conn).get_columns(tabelle) if c["name"] == "erstellt_via")
                assert spalte["nullable"] is True and spalte["default"] is None
            mandant = conn.execute(
                text("INSERT INTO mandanten (name, slug, status) VALUES ('M', 'm-0120-' || gen_random_uuid(), 'aktiv') RETURNING id")
            ).scalar_one()
            # Ohne Angabe bleibt die Spalte NULL (kein Backfill, kein Default); die Anwendung deutet NULL als 'app'.
            conn.execute(
                text("INSERT INTO form_schemas (mandant_id, name) VALUES (:m, 'ohne')"), {"m": mandant}
            )
            conn.execute(
                text("INSERT INTO form_schemas (mandant_id, name, erstellt_via) VALUES (:m, 'ki', 'ki')"), {"m": mandant}
            )
            assert conn.execute(text("SELECT erstellt_via FROM form_schemas WHERE name = 'ohne'")).scalar() is None
            conn.commit()
            with pytest.raises(IntegrityError):
                conn.execute(
                    text("INSERT INTO form_schemas (mandant_id, name, erstellt_via) VALUES (:m, 'x', 'mensch')"),
                    {"m": mandant},
                )
            conn.rollback()
            conn.execute(text("DELETE FROM form_schemas WHERE mandant_id = :m"), {"m": mandant})
            conn.execute(text("DELETE FROM mandanten WHERE id = :m"), {"m": mandant})
            conn.commit()

        # Zweiter Durchlauf bleibt sauber.
        await _migrieren("downgrade", "0119")
        await _migrieren("upgrade", "head")
        with engine.connect() as conn:
            for tabelle in _TABELLEN:
                assert "erstellt_via" in {c["name"] for c in inspect(conn).get_columns(tabelle)}
    finally:
        await _migrieren("upgrade", "head")
        engine.dispose()
