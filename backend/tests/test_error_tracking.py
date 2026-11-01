import logging

import httpx
import pytest
import sentry_sdk
from fastapi import FastAPI

from app.core import error_tracking
from app.core.config import get_settings
from app.core.error_tracking import init_error_tracking, scrub_breadcrumb, scrub_event
from app.core.logging_config import kontext_neu
from app.core.request_middleware import RequestKontextMiddleware

pytestmark = pytest.mark.filterwarnings("ignore:Function transports:DeprecationWarning")


@pytest.fixture(autouse=True)
def _sdk_zuruecksetzen():
    yield
    sentry_sdk.get_global_scope().set_client(None)
    sentry_sdk.get_isolation_scope().clear()


def test_ohne_dsn_wird_nichts_initialisiert(monkeypatch):
    monkeypatch.setattr(get_settings(), "sentry_dsn", None)
    assert init_error_tracking(komponente="backend") is False
    assert sentry_sdk.get_client().is_active() is False
    monkeypatch.setattr(get_settings(), "sentry_dsn", "   ")
    assert init_error_tracking(komponente="backend") is False


def test_ohne_dsn_wird_sdk_nicht_importiert(monkeypatch):
    # Kein Netzverkehr heisst auch: das Modul wird gar nicht erst geladen.
    monkeypatch.setattr(get_settings(), "sentry_dsn", "")
    aufgerufen = []
    monkeypatch.setattr(error_tracking.logger, "info", lambda *a, **k: aufgerufen.append(a))
    assert init_error_tracking(komponente="worker") is False
    assert aufgerufen == []


def test_init_setzt_release_environment_sampling_und_keine_pii(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "sentry_dsn", "https://publickey@errors.example.eu/7")
    monkeypatch.setattr(s, "sentry_release", "v1.2.3")
    monkeypatch.setattr(s, "sentry_environment", "staging")
    monkeypatch.setattr(s, "sentry_sample_rate", 0.5)
    monkeypatch.setattr(s, "sentry_traces_sample_rate", 0.0)
    assert init_error_tracking(komponente="backend", transport=lambda e: None) is True
    optionen = sentry_sdk.get_client().options
    assert optionen["release"] == "v1.2.3"
    assert optionen["environment"] == "staging"
    assert optionen["sample_rate"] == 0.5
    assert optionen["traces_sample_rate"] == 0.0
    assert optionen["send_default_pii"] is False
    assert optionen["max_request_body_size"] == "never"
    assert optionen["include_local_variables"] is False


def test_release_faellt_auf_git_commit_zurueck(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "sentry_dsn", "https://k@errors.example.eu/1")
    monkeypatch.setattr(s, "sentry_release", None)
    monkeypatch.setattr(s, "git_commit", "abc1234")
    init_error_tracking(komponente="backend", transport=lambda e: None)
    assert sentry_sdk.get_client().options["release"] == "abc1234"


def test_scrub_event_entfernt_bodies_cookies_query_header_und_user():
    event = {
        "request": {
            "url": "https://api.example.de/api/auth/reset?token=geheim123#frag",
            "query_string": "token=geheim123",
            "data": {"password": "hunter2", "iban": "DE89370400440532013000"},
            "cookies": {"refresh": "abc"},
            "headers": {"Authorization": "Bearer xyz", "Cookie": "a=b", "User-Agent": "UA", "X-Request-ID": "r1"},
            "env": {"REMOTE_ADDR": "1.2.3.4"},
        },
        "user": {"id": "u1", "email": "a@b.de", "ip_address": "1.2.3.4"},
        "server_name": "host-01",
        "exception": {"values": [{"value": "Login password=hunter2 fehlgeschlagen", "stacktrace": {"frames": [{"vars": {"x": 1}}]}}]},
        "breadcrumbs": {"values": [
            {"category": "query", "message": "SELECT * FROM users WHERE email='a@b.de'"},
            {"category": "logger", "message": "Authorization: Bearer abc.def", "data": {"x": 1}},
        ]},
    }
    bereinigt = scrub_event(event)
    req = bereinigt["request"]
    assert req["url"] == "https://api.example.de/api/auth/reset"
    assert "data" not in req and "cookies" not in req and "query_string" not in req and "env" not in req
    assert set(k.lower() for k in req["headers"]) == {"user-agent", "x-request-id"}
    assert "user" not in bereinigt and "server_name" not in bereinigt
    assert "hunter2" not in bereinigt["exception"]["values"][0]["value"]
    assert "vars" not in bereinigt["exception"]["values"][0]["stacktrace"]["frames"][0]
    krumen = bereinigt["breadcrumbs"]["values"]
    assert len(krumen) == 1 and "abc.def" not in krumen[0]["message"] and "data" not in krumen[0]


def test_scrub_event_haengt_request_id_aus_dem_log_kontext_an():
    kontext_neu(request_id="req-4711-abcd", mandant_id="m-1")
    assert scrub_event({})["tags"] == {"request_id": "req-4711-abcd", "mandant_id": "m-1"}


def test_scrub_breadcrumb_verwirft_sql_und_http_krumen():
    assert scrub_breadcrumb({"category": "query", "message": "SELECT 1"}) is None
    assert scrub_breadcrumb({"category": "httplib", "message": "GET x"}) is None
    krume = scrub_breadcrumb({"category": "logger", "message": "token=abc", "data": {"a": 1}})
    assert "abc" not in krume["message"] and "data" not in krume


async def test_unbehandelte_exception_wird_gemeldet_ohne_pii(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "sentry_dsn", "https://k@errors.example.eu/1")
    ereignisse: list[dict] = []
    assert init_error_tracking(komponente="backend", transport=ereignisse.append)

    app = FastAPI()
    app.add_middleware(RequestKontextMiddleware)

    @app.post("/boom")
    async def boom():
        raise RuntimeError("kaputt token=supersecret")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/boom?access_token=querygeheim",
            json={"passwort": "hunter2", "iban": "DE89370400440532013000"},
            headers={"Authorization": "Bearer jwt.jwt.jwt", "Cookie": "refresh=abc", "X-Request-ID": "req-sentry-0001"},
        )
    assert resp.status_code == 500
    sentry_sdk.flush()
    assert ereignisse, "kein Event beim Transport angekommen"
    roh = str(ereignisse)
    for geheim in ("supersecret", "querygeheim", "hunter2", "DE89370400440532013000", "jwt.jwt.jwt", "refresh=abc"):
        assert geheim not in roh, geheim
    event = ereignisse[0]
    assert event["tags"]["request_id"] == "req-sentry-0001"
    assert event["tags"]["komponente"] == "backend"
    assert event["exception"]["values"][0]["type"] == "RuntimeError"


async def test_http_4xx_wird_nicht_gemeldet(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(get_settings(), "sentry_dsn", "https://k@errors.example.eu/1")
    ereignisse: list[dict] = []
    init_error_tracking(komponente="backend", transport=ereignisse.append)
    app = FastAPI()

    @app.get("/nein")
    async def nein():
        raise HTTPException(403, "Verboten")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/nein")).status_code == 403
    sentry_sdk.flush()
    assert ereignisse == []


def test_logger_error_wird_zum_event_info_nicht(monkeypatch):
    monkeypatch.setattr(get_settings(), "sentry_dsn", "https://k@errors.example.eu/1")
    ereignisse: list[dict] = []
    init_error_tracking(komponente="worker", transport=ereignisse.append)
    log = logging.getLogger("app.test_et")
    log.info("nur info")
    log.error("Job kaputt password=geheim")
    sentry_sdk.flush()
    assert len(ereignisse) == 1
    assert "geheim" not in str(ereignisse)
