"""Migration 0117: app.is_super_admin verschwindet aus allen Policies, Downgrade stellt sie exakt wieder her."""
import asyncio
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.core.config import get_settings

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cfg() -> Config:
    cfg = Config(os.path.join(_BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND, "alembic"))
    return cfg


async def _migrieren(richtung: str, ziel: str) -> None:
    await asyncio.to_thread(getattr(command, richtung), _cfg(), ziel)


def _snapshot(engine) -> list[tuple]:
    with engine.connect() as conn:
        return [
            tuple(r)
            for r in conn.execute(
                text(
                    "SELECT tablename, policyname, permissive, roles::text, cmd, qual, with_check "
                    "FROM pg_policies WHERE schemaname = 'public' ORDER BY tablename, policyname"
                )
            )
        ]


@pytest.mark.asyncio
async def test_migration_0117_bereinigt_policies_und_ist_reversibel():
    engine = create_engine(os.environ.get("DATABASE_URL_SYNC") or get_settings().database_url_sync)
    try:
        nachher = _snapshot(engine)
        assert nachher
        assert not [p for p in nachher if "is_super_admin" in f"{p[5]}{p[6]}"]
        tabellen = {p[0] for p in nachher}
        # Beide Policies entfallen: die Tabelle bleibt ohne Policy (RLS+FORCE).
        assert "plattform_integrationen" not in tabellen
        # Namen und Befehlstyp bleiben erhalten, die Mandantenbedingung auch.
        isolation = [p for p in nachher if p[1] == "mandant_isolation"]
        assert len(isolation) > 100
        assert all(p[4] == "ALL" and "app.current_mandant" in p[5] and p[6] for p in isolation)

        await _migrieren("downgrade", "0116")
        vorher = _snapshot(engine)
        assert {p[1] for p in vorher if p[0] == "plattform_integrationen"} == {
            "plattform_integrationen_lesbar",
            "plattform_integrationen_schreibbar",
        }
        assert all("is_super_admin" in f"{p[5]}{p[6]}" for p in vorher if p[1] != "plattform_integrationen_lesbar")
        assert len(vorher) == len(nachher) + 2

        await _migrieren("upgrade", "head")
        assert _snapshot(engine) == nachher

        await _migrieren("downgrade", "0116")
        assert _snapshot(engine) == vorher
    finally:
        await _migrieren("upgrade", "head")
        engine.dispose()
