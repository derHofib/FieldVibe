"""Migration 0114 (GoBD-Paket): up/down/up, Backfill des Altbestands, Trigger vorhanden."""
import asyncio
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.config import get_settings

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_NEUE_TABELLEN = {"audit_log_siegel", "s3_loeschauftraege", "mandant_exporte"}
_TRIGGER = {
    ("audit_log", "trg_audit_log_append_only"),
    ("audit_log_siegel", "trg_audit_log_siegel_append_only"),
    ("rechnungen", "trg_rechnungen_festschreibung"),
    ("rechnung_positionen", "trg_rechnung_positionen_festschreibung"),
}


def _cfg() -> Config:
    cfg = Config(os.path.join(_BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND, "alembic"))
    return cfg


async def _migrieren(richtung: str, ziel: str) -> None:
    await asyncio.to_thread(getattr(command, richtung), _cfg(), ziel)


def _engine():
    return create_engine(os.environ.get("DATABASE_URL_SYNC") or get_settings().database_url_sync)


def _trigger(conn) -> set[tuple[str, str]]:
    zeilen = conn.execute(
        text("SELECT c.relname, t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid WHERE NOT t.tgisinternal")
    )
    return {(r[0], r[1]) for r in zeilen}


@pytest.mark.asyncio
async def test_migration_0114_up_down_up_mit_backfill():
    engine = _engine()
    try:
        await _migrieren("downgrade", "0113")
        with engine.connect() as conn:
            assert not _NEUE_TABELLEN & set(inspect(conn).get_table_names())
            spalten = {c["name"] for c in inspect(conn).get_columns("audit_log")}
            assert not {"akteur_typ", "request_id", "ip", "legacy"} & spalten
            assert not {"pdf_sha256", "xml_sha256"} & {c["name"] for c in inspect(conn).get_columns("rechnungen")}
            assert not _TRIGGER & _trigger(conn)
            # Altbestand: Eintraege mit und ohne Akteur, noch ohne die neuen Spalten.
            conn.execute(text("SET app.is_super_admin = 'true'"))
            conn.execute(text("INSERT INTO audit_log (aktion, payload) VALUES ('alt_system', '{}'::jsonb)"))
            conn.commit()

        await _migrieren("upgrade", "head")
        with engine.connect() as conn:
            conn.execute(text("SET app.is_super_admin = 'true'"))
            assert _NEUE_TABELLEN <= set(inspect(conn).get_table_names())
            assert _TRIGGER <= _trigger(conn)
            zeile = conn.execute(text("SELECT akteur_typ, legacy FROM audit_log WHERE aktion = 'alt_system'")).one()
            assert zeile == ("system", True)  # ohne Akteur -> system; vor der Kette -> legacy
            # Neue Eintraege nach der Migration sind keine Altlast.
            conn.execute(text("INSERT INTO audit_log (aktion, payload) VALUES ('neu', '{}'::jsonb)"))
            assert conn.execute(text("SELECT legacy FROM audit_log WHERE aktion = 'neu'")).scalar() is False
            conn.rollback()
        # Zweiter Durchlauf bleibt sauber (down/up/down/up).
        await _migrieren("downgrade", "0113")
        await _migrieren("upgrade", "head")
    finally:
        await _migrieren("upgrade", "head")
        with engine.connect() as conn:
            conn.execute(text("SET app.is_super_admin = 'true'"))
            conn.execute(text("TRUNCATE audit_log RESTART IDENTITY CASCADE"))
            conn.commit()
        engine.dispose()
