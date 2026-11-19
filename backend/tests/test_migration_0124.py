"""Migration 0124 (kunde_betreuung): Spalte, partieller Unique-Index, Backfill, Downgrade."""
import asyncio
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from tests.conftest import sync_system_engine

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cfg() -> Config:
    cfg = Config(os.path.join(_BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND, "alembic"))
    return cfg


async def _migrieren(richtung: str, ziel: str) -> None:
    await asyncio.to_thread(getattr(command, richtung), _cfg(), ziel)


@pytest.mark.asyncio
async def test_migration_0124_backfill_index_und_downgrade():
    engine = sync_system_engine()
    try:
        await _migrieren("downgrade", "0121")
        with engine.connect() as conn:
            spalten = {c["name"] for c in inspect(conn).get_columns("kunde_zuweisungen")}
            assert "hauptbetreuer" not in spalten

            mandant = conn.execute(
                text("INSERT INTO mandanten (name, slug, status) VALUES ('M', 'm-0124-' || gen_random_uuid(), 'aktiv') RETURNING id")
            ).scalar_one()
            users = [
                conn.execute(
                    text("INSERT INTO users (mandant_id, email, password_hash, role, name) "
                         "VALUES (:m, gen_random_uuid() || '@example.de', 'x', 'mandant_admin', :n) RETURNING id"),
                    {"m": mandant, "n": f"U{i}"},
                ).scalar_one()
                for i in range(2)
            ]
            kunden = [
                conn.execute(
                    text("INSERT INTO kunden (mandant_id, kundennummer, name, portal_slug) "
                         "VALUES (:m, :nr, 'K', gen_random_uuid()::text) RETURNING id"),
                    {"m": mandant, "nr": f"K{i}"},
                ).scalar_one()
                for i in range(3)
            ]
            einzeln, zu_zweit, ohne = kunden
            for kunde, user in ((einzeln, users[0]), (zu_zweit, users[0]), (zu_zweit, users[1])):
                conn.execute(
                    text("INSERT INTO kunde_zuweisungen (mandant_id, kunde_id, user_id) VALUES (:m, :k, :u)"),
                    {"m": mandant, "k": kunde, "u": user},
                )
            conn.commit()

        await _migrieren("upgrade", "0124")
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT kunde_id, user_id, hauptbetreuer FROM kunde_zuweisungen WHERE mandant_id = :m"),
                {"m": mandant},
            ).all()
            haupt = {(r.kunde_id, r.user_id): r.hauptbetreuer for r in rows}
            assert haupt[(einzeln, users[0])] is True
            assert haupt[(zu_zweit, users[0])] is False
            assert haupt[(zu_zweit, users[1])] is False
            assert conn.execute(
                text("SELECT count(*) FROM pg_indexes WHERE indexname = 'uq_kunde_zuweisungen_haupt' "
                     "AND indexdef LIKE '%UNIQUE%' AND indexdef LIKE '%WHERE%hauptbetreuer%'")
            ).scalar_one() == 1
            # FORCE RLS ist nach dem Backfill wieder gesetzt.
            assert conn.execute(
                text("SELECT relforcerowsecurity FROM pg_class WHERE relname = 'kunde_zuweisungen'")
            ).scalar_one() is True

            conn.execute(
                text("UPDATE kunde_zuweisungen SET hauptbetreuer = true WHERE kunde_id = :k AND user_id = :u"),
                {"k": zu_zweit, "u": users[0]},
            )
            with pytest.raises(IntegrityError):
                conn.execute(
                    text("UPDATE kunde_zuweisungen SET hauptbetreuer = true WHERE kunde_id = :k AND user_id = :u"),
                    {"k": zu_zweit, "u": users[1]},
                )
            conn.rollback()

        await _migrieren("downgrade", "0121")
        with engine.connect() as conn:
            assert "hauptbetreuer" not in {c["name"] for c in inspect(conn).get_columns("kunde_zuweisungen")}
            assert conn.execute(
                text("SELECT count(*) FROM pg_indexes WHERE indexname = 'uq_kunde_zuweisungen_haupt'")
            ).scalar_one() == 0
    finally:
        await _migrieren("upgrade", "head")
        engine.dispose()
