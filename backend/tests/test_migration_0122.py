"""Migration 0122 (Aufgabe-Auftrag): up/down/up, Spalte, Constraints, Filter-Entitaet."""
import asyncio
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from tests.conftest import sync_system_engine

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cfg() -> Config:
    cfg = Config(os.path.join(_BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND, "alembic"))
    return cfg


async def _migrieren(richtung: str, ziel: str) -> None:
    await asyncio.to_thread(getattr(command, richtung), _cfg(), ziel)


@pytest.mark.asyncio
async def test_migration_0122_up_down_up():
    engine = sync_system_engine()
    try:
        await _migrieren("downgrade", "0121")
        with engine.connect() as conn:
            spalten = {c["name"] for c in inspect(conn).get_columns("projekt_aufgaben")}
            assert "auftrag_id" not in spalten

        await _migrieren("upgrade", "0122")
        with engine.connect() as conn:
            spalten = {c["name"] for c in inspect(conn).get_columns("projekt_aufgaben")}
            assert "auftrag_id" in spalten
            for name in ("ck_projekt_aufgaben_auftrag_oder_vorgang", "ck_gespeicherte_filter_entitaet_valid"):
                assert conn.execute(
                    text("SELECT count(*) FROM pg_constraint WHERE conname = :n"), {"n": name}
                ).scalar_one() == 1
            assert conn.execute(
                text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_gespeicherte_filter_entitaet_valid'")
            ).scalar_one().count("aufgaben") == 1
        await _migrieren("downgrade", "0121")
        await _migrieren("upgrade", "head")
    finally:
        engine.dispose()
