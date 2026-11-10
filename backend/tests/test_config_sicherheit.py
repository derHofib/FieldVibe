import pytest

from app.core.config import (
    MIN_JWT_SECRET_LAENGE,
    Settings,
    UnsichereKonfigurationError,
)

_STARKES_SECRET = "x" * 20 + "Zufall-Aa1" + "y" * 20

_SICHER = dict(
    jwt_secret=_STARKES_SECRET,
    integration_secret_key="i" * 40,
    s3_secret_key="s" * 40,
    database_url="postgresql+asyncpg://fieldvibe_app:3f9a8c7d6e5b4a3f@postgres:5432/fieldvibe",
    database_url_sync="postgresql+psycopg2://fieldvibe_app:3f9a8c7d6e5b4a3f@postgres:5432/fieldvibe",
)


def _settings(**kw) -> Settings:
    # _env_file=None: eine lokale .env darf das Ergebnis nicht beeinflussen.
    return Settings(_env_file=None, **kw)


def test_produktion_mit_starken_secrets_startet():
    s = _settings(environment="production", **_SICHER)
    assert not s.ist_dev_umgebung


def test_default_umgebung_ist_produktion(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    s = _settings(**_SICHER)
    assert s.environment == "production"
    with pytest.raises(UnsichereKonfigurationError):
        _settings(**{**_SICHER, "jwt_secret": "changeme"})


@pytest.mark.parametrize("secret", ["change-me-in-env", "changeme-generate-with-openssl-rand", "kurz"])
def test_produktion_bricht_bei_unsicherem_jwt_secret_ab(secret):
    with pytest.raises(UnsichereKonfigurationError, match="JWT_SECRET") as exc:
        _settings(environment="production", **{**_SICHER, "jwt_secret": secret})
    assert "ENVIRONMENT=development" in str(exc.value)


def test_mindestlaenge_grenzwert():
    _settings(environment="production", **{**_SICHER, "jwt_secret": "a" * MIN_JWT_SECRET_LAENGE})
    with pytest.raises(UnsichereKonfigurationError):
        _settings(environment="production", **{**_SICHER, "jwt_secret": "a" * (MIN_JWT_SECRET_LAENGE - 1)})


def test_produktion_bricht_bei_default_s3_secret_ab():
    with pytest.raises(UnsichereKonfigurationError, match="S3_SECRET_KEY"):
        _settings(environment="production", **{**_SICHER, "s3_secret_key": "changeme"})


def test_produktion_bricht_bei_platzhalter_integration_key_ab():
    with pytest.raises(UnsichereKonfigurationError, match="INTEGRATION_SECRET_KEY"):
        _settings(environment="production", **{**_SICHER, "integration_secret_key": "changeme-generate-with-openssl-rand"})


def test_fehlender_integration_key_bleibt_erlaubt():
    # Fallback auf JWT_SECRET: Bestand mit verschluesselten Integrations-Secrets.
    _settings(environment="production", **{**_SICHER, "integration_secret_key": None})


@pytest.mark.parametrize("pw", ["fieldvibe", "fieldvibe_app", "changeme-generate-with-openssl-rand"])
def test_produktion_bricht_bei_default_db_passwort_ab(pw):
    url = f"postgresql+asyncpg://fieldvibe_app:{pw}@postgres:5432/fieldvibe"
    with pytest.raises(UnsichereKonfigurationError, match="DATABASE_URL"):
        _settings(environment="production", **{**_SICHER, "database_url": url})


def test_meldung_nennt_alle_probleme_auf_einmal():
    with pytest.raises(UnsichereKonfigurationError) as exc:
        _settings(
            environment="production",
            jwt_secret="changeme",
            s3_secret_key="changeme",
            database_url="postgresql+asyncpg://fieldvibe:fieldvibe@postgres:5432/fieldvibe",
        )
    text = str(exc.value)
    assert "JWT_SECRET" in text and "S3_SECRET_KEY" in text and "DATABASE_URL" in text


@pytest.mark.parametrize("env", ["development", "test", "TESTING", "Local", " dev "])
def test_dev_und_test_bleiben_mit_defaults_lauffaehig(env):
    s = _settings(environment=env, jwt_secret="change-me-in-env", s3_secret_key="changeme")
    assert s.ist_dev_umgebung


def test_unbekannte_umgebung_gilt_als_produktion():
    with pytest.raises(UnsichereKonfigurationError):
        _settings(environment="staging")


def test_testlauf_nutzt_test_umgebung():
    # conftest setzt ENVIRONMENT=test; die laufende App-Konfiguration darf
    # nicht in den Produktionspfad fallen.
    from app.core.config import get_settings

    assert get_settings().ist_dev_umgebung
