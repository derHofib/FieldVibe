import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app import healthcheck
from app.core.config import get_settings
from app.db.session import system_session
from app.models.job_lauf import JobLauf
from app.services import health_service, heartbeat_service
from app.services.health_service import Pruefung
from app.services.job_state_service import heartbeat, lade_laeufe, markiere_lauf
from sqlalchemy import select
from tests.conftest import auth_headers, login


@pytest.fixture
def health_token(monkeypatch):
    monkeypatch.setattr(get_settings(), "health_token", "monitor-token-123")
    return {"Authorization": "Bearer monitor-token-123"}


async def test_health_liveness_ist_billig_und_offen(client):
    resp = await client.get("/health")
    assert resp.status_code == 200 and resp.json() == {"status": "ok"}


async def test_ready_ohne_ausweis_nur_status(client):
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_ready_mit_token_liefert_details(client, health_token):
    resp = await client.get("/health/ready", headers=health_token)
    body = resp.json()
    assert resp.status_code == 200
    assert body["pruefungen"]["datenbank"]["ok"] is True
    assert body["pruefungen"]["migration"]["ok"] is True
    assert body["migration_head"] == health_service.alembic_head()


async def test_ready_mit_falschem_token_liefert_keine_details(client, health_token):
    resp = await client.get("/health/ready", headers={"Authorization": "Bearer falsch"})
    assert resp.json() == {"status": "ok"}


async def test_ready_mit_super_admin_jwt_liefert_details(client, make_user):
    await make_user(mandant=None, role="super_admin", email="sa@example.de", password="pw-123456")
    token = await login(client, "sa@example.de", "pw-123456")
    resp = await client.get("/health/ready", headers=auth_headers(token))
    assert "pruefungen" in resp.json()


async def test_ready_ausstehende_migration_ist_503_ohne_leck(client, monkeypatch):
    monkeypatch.setattr(health_service, "alembic_head", lambda: "0001")
    resp = await client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json() == {"status": "nicht_bereit"}


async def test_ready_ausstehende_migration_detail_mit_token(client, monkeypatch, health_token):
    monkeypatch.setattr(health_service, "alembic_head", lambda: "0001")
    resp = await client.get("/health/ready", headers=health_token)
    assert resp.status_code == 503
    assert "Migration ausstehend" in resp.json()["pruefungen"]["migration"]["detail"]


async def test_ready_db_neuer_als_code_bleibt_bereit_rollback(client, monkeypatch, health_token):
    monkeypatch.setattr(health_service, "alembic_head", lambda: "0001")
    monkeypatch.setattr(health_service, "_kenne_revision", lambda rev: False)
    resp = await client.get("/health/ready", headers=health_token)
    assert resp.status_code == 200
    assert "Rollback" in resp.json()["pruefungen"]["migration"]["detail"]


async def test_ready_s3_ausfall_ist_503_und_leakt_keinen_host(client, monkeypatch):
    async def kaputt():
        return Pruefung(False, "Objektspeicher nicht erreichbar")

    monkeypatch.setattr(health_service, "pruefe_s3", kaputt)
    resp = await client.get("/health/ready")
    assert resp.status_code == 503
    assert "localhost" not in resp.text and "9401" not in resp.text


async def test_heartbeats_ohne_ausweis_404(client):
    assert (await client.get("/health/heartbeats")).status_code == 404
    resp = await client.get("/health/heartbeats", headers={"Authorization": "Bearer falsch"})
    assert resp.status_code == 404


async def test_heartbeats_worker_frisch_ok_und_veraltet_fehler(client, health_token):
    await heartbeat("worker_tick")
    resp = await client.get("/health/heartbeats", headers=health_token)
    worker = next(h for h in resp.json()["heartbeats"] if h["name"] == "worker_tick")
    assert worker["status"] == "ok" and worker["alter_sekunden"] < 30

    alt = datetime.now(timezone.utc) - timedelta(minutes=10)
    await heartbeat("worker_tick", jetzt=alt)
    resp = await client.get("/health/heartbeats", headers=health_token)
    worker = next(h for h in resp.json()["heartbeats"] if h["name"] == "worker_tick")
    assert worker["status"] == "fehler"
    assert resp.status_code == 503 and resp.json()["status"] == "fehler"


async def test_heartbeats_worker_nie_gelaufen_ist_fehler(client, health_token):
    resp = await client.get("/health/heartbeats", headers=health_token)
    worker = next(h for h in resp.json()["heartbeats"] if h["name"] == "worker_tick")
    assert worker["status"] == "fehler" and worker["letzter_lauf"] is None


async def test_heartbeats_backup_alter_und_fehlerstatus(client, health_token, monkeypatch, tmp_path):
    datei = tmp_path / "letzter-lauf.json"
    monkeypatch.setattr(get_settings(), "backup_status_datei", str(datei))
    jetzt = datetime.now(timezone.utc)

    datei.write_text(json.dumps({"zeitpunkt": jetzt.isoformat(), "status": "ok"}))
    eintraege = await health_service.heartbeats()
    assert next(e for e in eintraege if e["name"] == "backup")["status"] == "ok"

    datei.write_text(json.dumps({"zeitpunkt": (jetzt - timedelta(hours=40)).isoformat(), "status": "ok"}))
    assert next(e for e in await health_service.heartbeats() if e["name"] == "backup")["status"] == "fehler"

    datei.write_text(json.dumps({"zeitpunkt": jetzt.isoformat(), "status": "fehler"}))
    backup = next(e for e in await health_service.heartbeats() if e["name"] == "backup")
    assert backup["status"] == "fehler" and "fehlgeschlagen" in backup["hinweis"]

    datei.write_text("kein json")
    assert next(e for e in await health_service.heartbeats() if e["name"] == "backup")["status"] == "fehler"


async def test_heartbeats_mail_konten_veraltet_je_mandant(make_mandant, make_user):
    from app.models.mail_account import MailAccount

    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin")
    async with system_session() as session:
        session.add(MailAccount(
            mandant_id=mandant.id, user_id=user.id, name="Info", email_adresse="info@example.de",
            imap_host="imap.example.de", imap_benutzername="info", smtp_host="smtp.example.de",
            smtp_benutzername="info", passwort_verschluesselt="x",
            letzter_sync_am=datetime.now(timezone.utc) - timedelta(hours=3),
        ))
    eintraege = {e["name"]: e for e in await health_service.heartbeats()}
    assert eintraege["mail_konten"]["status"] == "warnung"
    assert eintraege["mail_konten"]["mandanten_betroffen"] == [str(mandant.id)]
    assert eintraege["mail_sync"]["status"] == "fehler"


def test_gesamtstatus_rangfolge():
    assert health_service.gesamtstatus([{"status": "ok"}, {"status": "aus"}]) == "ok"
    assert health_service.gesamtstatus([{"status": "ok"}, {"status": "warnung"}]) == "warnung"
    assert health_service.gesamtstatus([{"status": "warnung"}, {"status": "fehler"}]) == "fehler"


def test_alarme_nur_bei_zustandswechsel_geloggt(caplog):
    health_service._letzter_alarmstand.clear()
    caplog.set_level(logging.INFO, logger="app.heartbeat")
    fehler = [{"name": "worker_tick", "status": "fehler", "hinweis": "seit 10 min"}]
    health_service.protokolliere_alarme(fehler)
    health_service.protokolliere_alarme(fehler)
    alarme = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(alarme) == 1 and "worker_tick" in alarme[0].getMessage()
    health_service.protokolliere_alarme([{"name": "worker_tick", "status": "ok"}])
    assert "wieder in Ordnung" in caplog.records[-1].getMessage()


async def test_markiere_lauf_upsert_system_und_mandant(make_mandant):
    mandant = await make_mandant()
    async with system_session() as session:
        await markiere_lauf(session, "demo", None, erfolg=True, ergebnis={"n": 1})
        await markiere_lauf(session, "demo", None, erfolg=True, ergebnis={"n": 2})
        await markiere_lauf(session, "demo", mandant.id, erfolg=False, fehler="kaputt")
        await markiere_lauf(session, "demo", mandant.id, erfolg=False, fehler="immer noch")
    async with system_session() as session:
        laeufe = await lade_laeufe(session, "demo")
        assert len(laeufe) == 2
        assert laeufe[None].ergebnis == {"n": 2} and laeufe[None].fehler_in_folge == 0
        m = laeufe[mandant.id]
        assert m.fehler_in_folge == 2 and m.letzter_fehler == "immer noch" and m.letzter_lauf_am is None
    async with system_session() as session:
        await markiere_lauf(session, "demo", mandant.id, erfolg=True)
    async with system_session() as session:
        m = (await lade_laeufe(session, "demo"))[mandant.id]
        assert m.fehler_in_folge == 0 and m.letzter_fehler is None and m.letzter_lauf_am is not None
        assert (await session.execute(select(JobLauf).where(JobLauf.job == "demo"))).scalars().all().__len__() == 2


def test_healthcheck_worker_datei_alter(tmp_path):
    datei = tmp_path / "hb"
    assert healthcheck.pruefe_worker(str(datei)) is False
    heartbeat_service.schreibe_heartbeat_datei(str(datei))
    assert healthcheck.pruefe_worker(str(datei)) is True
    alt = time.time() - 600
    os.utime(datei, (alt, alt))
    assert healthcheck.pruefe_worker(str(datei)) is False


def test_healthcheck_cli_exit_codes(monkeypatch):
    monkeypatch.setattr(healthcheck, "pruefe_backend", lambda: True)
    assert healthcheck.main(["backend"]) == 0
    monkeypatch.setattr(healthcheck, "pruefe_backend", lambda: False)
    assert healthcheck.main(["backend"]) == 1
    assert healthcheck.main(["unbekannt"]) == 2


async def test_heartbeat_einmal_ohne_ping_url_macht_keinen_netzverkehr(monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "worker_heartbeat_datei", str(tmp_path / "hb"))
    monkeypatch.setattr(settings, "heartbeat_ping_url", None)

    async def verboten(url):
        raise AssertionError("Ping trotz leerer URL")

    monkeypatch.setattr(heartbeat_service, "pinge_extern", verboten)
    assert await heartbeat_service.heartbeat_einmal(letzter_ping=None) is None
    assert (tmp_path / "hb").exists()


async def test_heartbeat_einmal_pingt_im_intervall(monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "worker_heartbeat_datei", str(tmp_path / "hb"))
    monkeypatch.setattr(settings, "heartbeat_ping_url", "https://hc.example/abc")
    aufrufe: list[str] = []

    async def merke(url):
        aufrufe.append(url)
        return True

    monkeypatch.setattr(heartbeat_service, "pinge_extern", merke)
    erster = await heartbeat_service.heartbeat_einmal(letzter_ping=None)
    zweiter = await heartbeat_service.heartbeat_einmal(letzter_ping=erster)
    assert aufrufe == ["https://hc.example/abc"] and zweiter == erster


async def test_pinge_extern_loggt_keine_url(monkeypatch, caplog):
    class Client(httpx.AsyncClient):
        def __init__(self, **kw):
            super().__init__(transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("boom https://hc.example/geheim"))), **kw)

    monkeypatch.setattr(heartbeat_service.httpx, "AsyncClient", Client)
    caplog.set_level(logging.WARNING, logger="app.heartbeat")
    assert await heartbeat_service.pinge_extern("https://hc.example/geheim") is False
    assert "geheim" not in caplog.text
