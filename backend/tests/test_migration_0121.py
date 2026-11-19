"""Migration 0121 (telefonate): up/down/up, RLS + Trigger, Event-Typ-Constraint."""
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
async def test_migration_0121_up_down_up():
    engine = sync_system_engine()
    try:
        await _migrieren("downgrade", "0120")
        with engine.connect() as conn:
            assert "telefonate" not in inspect(conn).get_table_names()

        await _migrieren("upgrade", "0121")
        with engine.connect() as conn:
            assert "telefonate" in inspect(conn).get_table_names()
            rls = conn.execute(
                text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'telefonate'")
            ).one()
            assert tuple(rls) == (True, True)
            assert conn.execute(
                text("SELECT count(*) FROM pg_policies WHERE tablename = 'telefonate' AND policyname = 'mandant_isolation'")
            ).scalar_one() == 1
            assert conn.execute(
                text("SELECT count(*) FROM pg_trigger WHERE tgname = 'trg_telefonate_updated_at'")
            ).scalar_one() == 1
            assert conn.execute(
                text("SELECT count(*) FROM pg_indexes WHERE tablename = 'telefonate' AND indexname = 'ix_telefonate_offene_rueckrufe' "
                     "AND indexdef LIKE '%rueckruf_erledigt_am IS NULL%'")
            ).scalar_one() == 1
            # Der neue Event-Typ ist zulaessig, ein unbekannter nicht.
            mandant = conn.execute(
                text("INSERT INTO mandanten (name, slug, status) VALUES ('M', 'm-0121-' || gen_random_uuid(), 'aktiv') RETURNING id")
            ).scalar_one()
            vorgang_ok = conn.execute(
                text("INSERT INTO kunden (mandant_id, kundennummer, name, portal_slug) VALUES (:m, 'K1', 'K', gen_random_uuid()::text) RETURNING id"),
                {"m": mandant},
            ).scalar_one()
            vorgang = conn.execute(
                text("INSERT INTO vorgaenge (mandant_id, vorgangsnummer, kunde_id, titel, abrechnungsart, leistungstyp) "
                     "VALUES (:m, 'V1', :k, 'T', 'aufwand', 'wartung') RETURNING id"),
                {"m": mandant, "k": vorgang_ok},
            ).scalar_one()
            conn.execute(
                text("INSERT INTO vorgang_events (mandant_id, vorgang_id, event_type, payload) VALUES (:m, :v, 'telefonat', '{}')"),
                {"m": mandant, "v": vorgang},
            )
            conn.commit()
            with pytest.raises(IntegrityError):
                conn.execute(
                    text("INSERT INTO vorgang_events (mandant_id, vorgang_id, event_type, payload) VALUES (:m, :v, 'unbekannt', '{}')"),
                    {"m": mandant, "v": vorgang},
                )
            conn.rollback()

        # Downgrade raeumt Telefonat-Events auf und stellt den alten Constraint her.
        await _migrieren("downgrade", "0120")
        with engine.connect() as conn:
            assert "telefonate" not in inspect(conn).get_table_names()
            definition = conn.execute(
                text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_vorgang_events_event_type_valid'")
            ).scalar_one()
            assert "telefonat" not in definition
            # Das Telefonat-Event wurde mit dem Downgrade entfernt, sonst haette der Constraint nicht gegriffen.
            assert conn.execute(
                text("SELECT count(*) FROM vorgang_events WHERE mandant_id = :m"), {"m": mandant}
            ).scalar_one() == 0
            conn.execute(text("DELETE FROM vorgang_events WHERE mandant_id = :m"), {"m": mandant})
            conn.execute(text("DELETE FROM vorgaenge WHERE mandant_id = :m"), {"m": mandant})
            conn.execute(text("DELETE FROM kunden WHERE mandant_id = :m"), {"m": mandant})
            conn.execute(text("DELETE FROM mandanten WHERE id = :m"), {"m": mandant})
            conn.commit()
        await _migrieren("upgrade", "head")
    finally:
        await _migrieren("upgrade", "head")
        engine.dispose()
