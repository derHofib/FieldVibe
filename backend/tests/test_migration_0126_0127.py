"""Migrationen 0126 (Leistungsort/Zeichen, Portal-Kontakte) und 0127 (Rechnungsempfaenger, verwaltet von, Telefonat-Kontakt)."""
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


def _spalten(conn, tabelle: str) -> set[str]:
    return {c["name"] for c in inspect(conn).get_columns(tabelle)}


@pytest.mark.asyncio
async def test_migration_0126_0127_upgrade_constraints_und_downgrade():
    engine = sync_system_engine()
    try:
        with engine.connect() as conn:
            for tabelle in ("rechnungen", "angebote"):
                assert {"kunden_referenz", "leistungsort"} <= _spalten(conn, tabelle)
            assert {"einheit", "kunden_referenz", "vor_ort_kontakte"} <= _spalten(conn, "vorgang_anfragen")
            assert "rechnung_an_kunde_id" in _spalten(conn, "auftraege") | _spalten(conn, "projekte")
            assert "verwaltet_von_kunde_id" in _spalten(conn, "kunden")
            assert "vor_ort_kontakt_id" in _spalten(conn, "telefonate")

            mandant = conn.execute(
                text("INSERT INTO mandanten (name, slug, status) VALUES ('M', 'm-0127-' || gen_random_uuid(), 'aktiv') RETURNING id")
            ).scalar_one()
            kunde = conn.execute(
                text("INSERT INTO kunden (mandant_id, kundennummer, name, portal_slug) VALUES (:m, 'K1', 'K', gen_random_uuid()::text) RETURNING id"),
                {"m": mandant},
            ).scalar_one()
            conn.commit()
            # Ein Kunde kann nicht sein eigener Verwalter.
            with pytest.raises(IntegrityError):
                conn.execute(text("UPDATE kunden SET verwaltet_von_kunde_id = id WHERE id = :k"), {"k": kunde})
            conn.rollback()
            # vor_ort_kontakte der Anfrage hat den Default [] (nicht NULL).
            assert conn.execute(text("SELECT column_default FROM information_schema.columns WHERE table_name='vorgang_anfragen' AND column_name='vor_ort_kontakte'")).scalar_one().startswith("'[]'")
            conn.execute(text("DELETE FROM kunden WHERE id = :k"), {"k": kunde})
            conn.execute(text("DELETE FROM mandanten WHERE id = :m"), {"m": mandant})
            conn.commit()

        await _migrieren("downgrade", "0125")
        with engine.connect() as conn:
            assert "kunden_referenz" not in _spalten(conn, "rechnungen")
            assert "leistungsort" not in _spalten(conn, "angebote")
            assert "vor_ort_kontakte" not in _spalten(conn, "vorgang_anfragen")
            assert "rechnung_an_kunde_id" not in _spalten(conn, "auftraege")
            assert "verwaltet_von_kunde_id" not in _spalten(conn, "kunden")
            assert "vor_ort_kontakt_id" not in _spalten(conn, "telefonate")
    finally:
        await _migrieren("upgrade", "head")
        engine.dispose()
