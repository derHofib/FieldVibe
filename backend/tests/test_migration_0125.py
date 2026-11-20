"""Migration 0125 (vor_ort_kontakte): Tabellen, Spalten, Policy, Constraints, Downgrade."""
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
async def test_migration_0125_upgrade_constraints_und_downgrade():
    engine = sync_system_engine()
    try:
        with engine.connect() as conn:
            tabellen = set(inspect(conn).get_table_names())
            assert {"vor_ort_kontakte", "vor_ort_kontakt_zuordnungen"} <= tabellen
            assert conn.execute(text("SELECT vor_ort_kontakte_anonymisieren_monate FROM mandanten LIMIT 1")).first() in (None, (12,))
            mandant = conn.execute(
                text("INSERT INTO mandanten (name, slug, status) VALUES ('M', 'm-0125-' || gen_random_uuid(), 'aktiv') RETURNING id")
            ).scalar_one()
            kunde = conn.execute(
                text("INSERT INTO kunden (mandant_id, kundennummer, name, portal_slug) VALUES (:m, 'K1', 'K', gen_random_uuid()::text) RETURNING id"),
                {"m": mandant},
            ).scalar_one()
            conn.commit()
            # Name oder Telefon ist Pflicht, ausser anonymisiert; Rolle ist eingeschraenkt.
            for sql in (
                "INSERT INTO vor_ort_kontakte (mandant_id, kunde_id, rolle) VALUES (:m, :k, 'mieter')",
                "INSERT INTO vor_ort_kontakte (mandant_id, kunde_id, rolle, name) VALUES (:m, :k, 'chef', 'X')",
                "UPDATE mandanten SET vor_ort_kontakte_anonymisieren_monate = 2 WHERE id = :m",
            ):
                with pytest.raises(IntegrityError):
                    conn.execute(text(sql), {"m": mandant, "k": kunde})
                conn.rollback()
            conn.execute(
                text("INSERT INTO vor_ort_kontakte (mandant_id, kunde_id, rolle, anonymisiert_am) VALUES (:m, :k, 'mieter', now())"),
                {"m": mandant, "k": kunde},
            )
            conn.commit()
            # Zuordnung braucht genau ein Ziel.
            kontakt = conn.execute(text("SELECT id FROM vor_ort_kontakte")).scalar_one()
            with pytest.raises(IntegrityError):
                conn.execute(
                    text("INSERT INTO vor_ort_kontakt_zuordnungen (mandant_id, kontakt_id) VALUES (:m, :c)"),
                    {"m": mandant, "c": kontakt},
                )
            conn.rollback()
            conn.execute(text("DELETE FROM vor_ort_kontakte"))
            conn.execute(text("DELETE FROM kunden WHERE id = :k"), {"k": kunde})
            conn.execute(text("DELETE FROM mandanten WHERE id = :m"), {"m": mandant})
            conn.commit()

        await _migrieren("downgrade", "0124")
        with engine.connect() as conn:
            insp = inspect(conn)
            assert "vor_ort_kontakte" not in insp.get_table_names()
            assert "standort_id" not in {c["name"] for c in insp.get_columns("auftraege")}
            assert "kunde_id" not in {c["name"] for c in insp.get_columns("projekte")}
            assert "einheit" not in {c["name"] for c in insp.get_columns("vorgaenge")}
            assert "vor_ort_kontakte_anonymisieren_monate" not in {c["name"] for c in insp.get_columns("mandanten")}
    finally:
        await _migrieren("upgrade", "head")
        engine.dispose()
