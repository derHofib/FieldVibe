"""Migrationen 0128 (ki_aktionen, ki_regeln) und 0129 (erstellt_via): Tabellen, Constraints, Policy, Downgrade."""
import asyncio
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from tests.conftest import sync_system_engine

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TABELLEN_VIA = ("vorgaenge", "auftraege", "projekte", "angebote", "rechnungen", "termine")


def _cfg() -> Config:
    cfg = Config(os.path.join(_BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND, "alembic"))
    return cfg


async def _migrieren(richtung: str, ziel: str) -> None:
    await asyncio.to_thread(getattr(command, richtung), _cfg(), ziel)


def _spalten(conn, tabelle: str) -> set[str]:
    return {c["name"] for c in inspect(conn).get_columns(tabelle)}


@pytest.mark.asyncio
async def test_migration_0128_0129_upgrade_constraints_und_downgrade():
    engine = sync_system_engine()
    try:
        with engine.connect() as conn:
            assert {"ki_aktionen", "ki_regeln"} <= set(inspect(conn).get_table_names())
            for tabelle in _TABELLEN_VIA:
                assert "erstellt_via" in _spalten(conn, tabelle), tabelle
            # RLS ist erzwungen, der updated_at-Trigger haengt an ki_aktionen.
            for tabelle in ("ki_aktionen", "ki_regeln"):
                assert conn.execute(
                    text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname = :t"), {"t": tabelle}
                ).scalar_one()
            assert conn.execute(
                text("SELECT count(*) FROM pg_trigger WHERE tgname = 'trg_ki_aktionen_updated_at'")
            ).scalar_one() == 1

            mandant = conn.execute(
                text("INSERT INTO mandanten (name, slug, status) VALUES ('M', 'm-0128-' || gen_random_uuid(), 'aktiv') RETURNING id")
            ).scalar_one()
            user = conn.execute(
                text("INSERT INTO users (mandant_id, email, password_hash, role, name) "
                     "VALUES (:m, gen_random_uuid() || '@example.de', 'x', 'mandant_admin', 'U') RETURNING id"),
                {"m": mandant},
            ).scalar_one()
            conn.commit()

            basis = {"m": mandant, "u": user}
            insert = (
                "INSERT INTO ki_aktionen (mandant_id, user_id, tool, aktionsart, stufe, status, zusammenfassung) "
                "VALUES (:m, :u, 't', 'vorgang.verknuepfen', {stufe}, '{status}', 'z')"
            )
            # Stufe 1-3 und die sechs Status sind erlaubt, alles andere nicht.
            conn.execute(text(insert.format(stufe=2, status="ausgefuehrt")), basis)
            conn.commit()
            for stufe, status in ((0, "ausgefuehrt"), (4, "ausgefuehrt"), (2, "unbekannt")):
                with pytest.raises(IntegrityError):
                    conn.execute(text(insert.format(stufe=stufe, status=status)), basis)
                conn.rollback()
            zeile = conn.execute(text("SELECT ziele, aenderungen, erzeugt, rueckweg FROM ki_aktionen")).one()
            assert list(zeile) == [[], [], [], []]

            with pytest.raises(IntegrityError):
                conn.execute(
                    text("INSERT INTO ki_regeln (mandant_id, aktionsart, modus) VALUES (:m, 'x', 'egal')"), basis
                )
            conn.rollback()
            conn.execute(text("INSERT INTO ki_regeln (mandant_id, aktionsart, modus, tageslimit) VALUES (:m, 'x', 'chat', 5)"), basis)
            with pytest.raises(IntegrityError):
                conn.execute(text("INSERT INTO ki_regeln (mandant_id, aktionsart, modus) VALUES (:m, 'x', 'aus')"), basis)
            conn.rollback()

            for tabelle in _TABELLEN_VIA:
                assert conn.execute(
                    text("SELECT column_default FROM information_schema.columns WHERE table_name = :t AND column_name = 'erstellt_via'"),
                    {"t": tabelle},
                ).scalar_one().startswith("'app'")
                assert conn.execute(
                    text("SELECT count(*) FROM pg_constraint WHERE conname = :c"), {"c": f"ck_{tabelle}_erstellt_via_valid"}
                ).scalar_one() == 1

            conn.execute(text("DELETE FROM ki_regeln WHERE mandant_id = :m"), basis)
            conn.execute(text("DELETE FROM ki_aktionen WHERE mandant_id = :m"), basis)
            conn.execute(text("DELETE FROM users WHERE id = :u"), basis)
            conn.execute(text("DELETE FROM mandanten WHERE id = :m"), basis)
            conn.commit()

        await _migrieren("downgrade", "0127")
        with engine.connect() as conn:
            assert not {"ki_aktionen", "ki_regeln"} & set(inspect(conn).get_table_names())
            for tabelle in _TABELLEN_VIA:
                assert "erstellt_via" not in _spalten(conn, tabelle), tabelle
    finally:
        await _migrieren("upgrade", "head")
        engine.dispose()
