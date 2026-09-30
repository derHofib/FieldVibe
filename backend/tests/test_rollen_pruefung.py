import logging
from types import SimpleNamespace

import pytest

from app.db import rollen_pruefung
from app.db.rollen_pruefung import UnsichereDbRolleError, pruefe_db_rolle
from app.db.session import engine


class _Ergebnis:
    def __init__(self, row):
        self._row = row

    def one(self):
        return self._row


class _Conn:
    def __init__(self, row):
        self._row = row

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, _stmt):
        return _Ergebnis(self._row)


class _FakeEngine:
    def __init__(self, *, rolsuper=False, rolbypassrls=False):
        self._row = SimpleNamespace(name="app_rolle", rolsuper=rolsuper, rolbypassrls=rolbypassrls)

    def connect(self):
        return _Conn(self._row)


def _override(monkeypatch, erlaubt: bool):
    monkeypatch.setattr(
        rollen_pruefung, "get_settings", lambda: SimpleNamespace(erlaube_rls_bypass_rolle=erlaubt)
    )


@pytest.mark.asyncio
async def test_superuser_bricht_ab(monkeypatch):
    _override(monkeypatch, False)
    with pytest.raises(UnsichereDbRolleError, match="app_rolle.*Superuser/BYPASSRLS"):
        await pruefe_db_rolle(_FakeEngine(rolsuper=True))


@pytest.mark.asyncio
async def test_bypassrls_bricht_ab(monkeypatch):
    _override(monkeypatch, False)
    with pytest.raises(UnsichereDbRolleError):
        await pruefe_db_rolle(_FakeEngine(rolbypassrls=True))


@pytest.mark.asyncio
async def test_env_override_warnt_und_startet(monkeypatch, caplog):
    _override(monkeypatch, True)
    # alembic/env.py ruft fileConfig() auf und deaktiviert dabei bereits
    # importierte Logger.
    monkeypatch.setattr(rollen_pruefung.logger, "disabled", False)
    with caplog.at_level(logging.WARNING, logger="app.db.rollen_pruefung"):
        await pruefe_db_rolle(_FakeEngine(rolsuper=True))
    assert any(r.levelno == logging.WARNING and "AUSSER KRAFT" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_normale_rolle_ok(monkeypatch, caplog):
    _override(monkeypatch, False)
    with caplog.at_level(logging.WARNING):
        await pruefe_db_rolle(_FakeEngine())
    assert not caplog.records


@pytest.mark.asyncio
async def test_echte_test_rolle_besteht_pruefung():
    await pruefe_db_rolle(engine)


def test_settings_liest_env_variable(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("FIELDVIBE_ERLAUBE_RLS_BYPASS_ROLLE", "1")
    assert Settings().erlaube_rls_bypass_rolle is True
    monkeypatch.delenv("FIELDVIBE_ERLAUBE_RLS_BYPASS_ROLLE")
    assert Settings().erlaube_rls_bypass_rolle is False
