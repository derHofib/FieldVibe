import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import docs_optionen

_PFADE = ("/docs", "/redoc", "/openapi.json")


def _app(**settings_kw) -> FastAPI:
    # Dev-Umgebung nur fuer den Settings-Aufbau (Platzhalter-Secrets); die
    # Doku-Sichtbarkeit steuern die uebergebenen Werte.
    s = Settings(_env_file=None, **settings_kw)
    return FastAPI(**docs_optionen(s))


async def _status(app: FastAPI) -> dict[str, int]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return {pfad: (await ac.get(pfad)).status_code for pfad in _PFADE}


async def test_doku_in_dev_an():
    assert await _status(_app(environment="development")) == dict.fromkeys(_PFADE, 200)


async def test_doku_in_produktion_aus():
    s = Settings(
        _env_file=None,
        environment="production",
        jwt_secret="s" * 48,
        s3_secret_key="s" * 40,
        database_url="postgresql+asyncpg://u:3f9a8c7d6e5b4a3f@db:5432/x",
        database_url_sync="postgresql+psycopg2://u:3f9a8c7d6e5b4a3f@db:5432/x",
    )
    assert not s.api_docs_aktiv
    app = FastAPI(**docs_optionen(s))
    assert await _status(app) == dict.fromkeys(_PFADE, 404)


async def test_setting_kann_doku_in_dev_abschalten():
    assert await _status(_app(environment="development", FIELDVIBE_API_DOCS=False)) == dict.fromkeys(_PFADE, 404)


def test_setting_kann_doku_explizit_einschalten(monkeypatch):
    monkeypatch.setenv("FIELDVIBE_API_DOCS", "1")
    assert Settings(_env_file=None, environment="development").api_docs_aktiv is True


@pytest.mark.parametrize("pfad", _PFADE)
async def test_testumgebung_der_echten_app_hat_doku(client, pfad):
    assert (await client.get(pfad)).status_code == 200
