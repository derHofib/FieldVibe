import json
import logging
import sys

import pytest

from app.core.logging_config import (
    JsonFormatter,
    KontextFilter,
    TextFormatter,
    job_kontext,
    konfiguriere_logging,
    kontext_ergaenzen,
    kontext_holen,
    kontext_neu,
    schwaerze,
)
from tests.conftest import auth_headers, login


def _record(msg="Hallo %s", args=("Welt",), level=logging.INFO, **extra):
    r = logging.LogRecord("app.test", level, __file__, 1, msg, args, None)
    for k, v in extra.items():
        setattr(r, k, v)
    return r


def test_json_format_enthaelt_kontext_und_ist_gueltiges_json():
    kontext_neu(request_id="abc12345")
    kontext_ergaenzen(user_id="u-1", mandant_id="m-1")
    r = _record()
    KontextFilter().filter(r)
    daten = json.loads(JsonFormatter().format(r))
    assert daten["message"] == "Hallo Welt"
    assert daten["level"] == "INFO"
    assert daten["request_id"] == "abc12345"
    assert daten["user_id"] == "u-1" and daten["mandant_id"] == "m-1"
    assert daten["ts"].endswith("+00:00")


def test_json_gibt_unbekannte_extras_nicht_aus():
    r = _record(body="geheim", authorization="Bearer xyz", path="/api/x", status=200)
    daten = json.loads(JsonFormatter().format(r))
    assert "body" not in daten and "authorization" not in daten
    assert daten["path"] == "/api/x" and daten["status"] == 200


def test_schwaerzung_von_zugangsdaten_in_meldungen():
    assert "hunter2" not in schwaerze("login failed password=hunter2 user=x")
    assert "abc.def" not in schwaerze("Authorization: Bearer abc.def")
    assert ":pw@" not in schwaerze("postgresql://user:pw@host/db")
    assert "DE89" not in schwaerze('iban: "DE89370400440532013000"')
    assert schwaerze("token_version=3") == "token_version=3"


def test_exception_wird_als_exc_feld_ausgegeben():
    try:
        raise ValueError("kaputt")
    except ValueError:
        r = _record()
        r.exc_info = sys.exc_info()
    daten = json.loads(JsonFormatter().format(r))
    assert "ValueError: kaputt" in daten["exc"]


def test_text_format_mit_kontext():
    kontext_neu(request_id="req-0001")
    r = _record()
    KontextFilter().filter(r)
    zeile = TextFormatter().format(r)
    assert "Hallo Welt" in zeile and "request_id=req-0001" in zeile


def test_job_kontext_setzt_und_entfernt_job_name():
    kontext_neu()
    with job_kontext("dauerauftraege"):
        assert kontext_holen()["job"] == "dauerauftraege"
    assert "job" not in kontext_holen()


def test_konfiguriere_logging_legt_uvicorn_access_still():
    root = logging.getLogger()
    alt = (list(root.handlers), root.level)
    try:
        konfiguriere_logging(format="json", level="WARNING")
        assert logging.getLogger("uvicorn.access").disabled is True
        assert logging.getLogger("uvicorn.error").propagate is True
        assert len(root.handlers) == 1 and isinstance(root.handlers[0].formatter, JsonFormatter)
    finally:
        root.handlers[:] = alt[0]
        root.setLevel(alt[1])
        logging.getLogger("uvicorn.access").disabled = False


async def test_antwort_traegt_neue_request_id(client):
    resp = await client.get("/healthz")
    rid = resp.headers["x-request-id"]
    assert len(rid) == 32
    resp2 = await client.get("/healthz")
    assert resp2.headers["x-request-id"] != rid


async def test_eingehende_request_id_wird_uebernommen_wenn_unverfaenglich(client):
    resp = await client.get("/healthz", headers={"X-Request-ID": "proxy-req-12345"})
    assert resp.headers["x-request-id"] == "proxy-req-12345"


@pytest.mark.parametrize("boese", ["kurz", "a" * 65, "<script>alert(1)</script>"])
async def test_unverfaengliche_request_id_wird_ersetzt(client, boese):
    resp = await client.get("/healthz", headers={"X-Request-ID": boese})
    assert resp.headers["x-request-id"] != boese


async def test_zugriffslog_mit_ids_ohne_query_und_ohne_token(client, make_mandant, make_user, caplog):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", email="log@example.de")
    token = await login(client, "log@example.de", user._plaintext_password)
    caplog.set_level(logging.INFO, logger="app.access")
    resp = await client.get("/api/auth/me?secret=querywert", headers=auth_headers(token))
    zeilen = [r for r in caplog.records if r.name == "app.access" and getattr(r, "path", "") == "/api/auth/me"]
    assert zeilen, [r.getMessage() for r in caplog.records]
    r = zeilen[-1]
    assert r.status == resp.status_code and r.method == "GET"
    assert r.user_id == str(user.id) and r.mandant_id == str(mandant.id)
    assert r.request_id == resp.headers["x-request-id"]
    ausgabe = JsonFormatter().format(r)
    assert "querywert" not in ausgabe and token not in ausgabe


async def test_health_wird_nicht_protokolliert(client, caplog):
    caplog.set_level(logging.INFO, logger="app.access")
    await client.get("/healthz")
    assert not [r for r in caplog.records if r.name == "app.access"]
