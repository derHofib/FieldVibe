from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, update

from app.db.session import system_session
from app.models.mail_outbox import MailOutbox
from app.models.notification import Notification
from app.models.sla import SlaEskalation
from app.models.vorgang import Vorgang
from app.services import job_runner
from app.services.job_runner import fuehre_tick
from app.services.sla_service import run_sla_eskalation
from tests.conftest import auth_headers, login

PW = "pw-123456"
STUFEN = [
    {"frist_art": "reaktion", "schwelle_prozent": 75, "aktion": "benachrichtigen", "empfaenger": "zugewiesener"},
    {"frist_art": "reaktion", "schwelle_prozent": 100, "aktion": "mail", "empfaenger": "admin"},
    {"frist_art": "loesung", "schwelle_prozent": 100, "aktion": "benachrichtigen", "empfaenger": "admin"},
]


async def _aufbau(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW)
    h = auth_headers(await login(client, admin.email, PW))
    kunde = await make_kunde(mandant=mandant)
    r = await client.post(
        "/api/sla/richtlinien", headers=h,
        json={"name": "S", "ist_standard": True, "ziele": {"3": {"reaktion_min": 60, "loesung_min": 240}}, "stufen": STUFEN},
    )
    assert r.status_code == 201, r.text
    v = await client.post(
        "/api/vorgaenge", headers=h,
        json={"kunde_id": str(kunde.id), "titel": "T", "abrechnungsart": "aufwand", "leistungstyp": "stoerung"},
    )
    return mandant, admin, h, v.json()["id"]


async def _laeuft_seit(vorgang_id, vor_minuten: int) -> None:
    async with system_session() as session:
        await session.execute(
            update(Vorgang).where(Vorgang.id == vorgang_id)
            .values(sla_laeuft_seit=datetime.now(timezone.utc) - timedelta(minutes=vor_minuten))
        )


async def _zaehle(modell, mandant_id) -> int:
    async with system_session() as session:
        return await session.scalar(select(func.count()).select_from(modell).where(modell.mandant_id == mandant_id))


@pytest.mark.asyncio
async def test_stufen_feuern_genau_einmal(client, make_mandant, make_user, make_kunde):
    mandant, admin, h, vid = await _aufbau(client, make_mandant, make_user, make_kunde)
    # Noch nichts faellig.
    assert (await run_sla_eskalation())["eskalationen"] == 0

    await _laeuft_seit(vid, 50)  # 83 % der Reaktionsfrist
    assert (await run_sla_eskalation())["eskalationen"] == 1
    assert (await run_sla_eskalation())["eskalationen"] == 0  # idempotent
    assert await _zaehle(SlaEskalation, mandant.id) == 1
    assert await _zaehle(MailOutbox, mandant.id) == 0

    await _laeuft_seit(vid, 70)  # Reaktionsfrist verletzt -> Mailstufe
    assert (await run_sla_eskalation())["eskalationen"] == 1
    assert await _zaehle(MailOutbox, mandant.id) == 1
    async with system_session() as session:
        typen = (await session.execute(select(Notification.typ, Notification.titel).where(Notification.mandant_id == mandant.id))).all()
    assert typen and all(t == "sla" for t, _ in typen)
    assert any("verletzt" in titel for _, titel in typen)


@pytest.mark.asyncio
async def test_reaktion_beendet_die_reaktionsstufen_nicht_die_loesung(client, make_mandant, make_user, make_kunde):
    mandant, admin, h, vid = await _aufbau(client, make_mandant, make_user, make_kunde)
    await client.post(f"/api/vorgaenge/{vid}/events", headers=h, json={"event_type": "kommentar", "body": "ok"})
    await _laeuft_seit(vid, 100)  # Reaktion laengst erledigt, Loesung bei 42 %
    assert (await run_sla_eskalation())["eskalationen"] == 0
    await _laeuft_seit(vid, 250)  # Loesungsfrist verletzt
    assert (await run_sla_eskalation())["eskalationen"] == 1


@pytest.mark.asyncio
async def test_pausierte_und_abgeschlossene_vorgaenge_bleiben_ruhig(client, make_mandant, make_user, make_kunde):
    mandant, admin, h, vid = await _aufbau(client, make_mandant, make_user, make_kunde)
    await client.patch(f"/api/vorgaenge/{vid}", headers=h, json={"status": "wartet_kunde"})
    async with system_session() as session:
        await session.execute(
            update(Vorgang).where(Vorgang.id == vid).values(sla_reaktion_verbraucht_min=500, sla_loesung_verbraucht_min=500)
        )
    assert (await run_sla_eskalation())["eskalationen"] == 0
    # Fortsetzen: verbrauchte Zeit zaehlt weiter -> sofort faellig.
    await client.patch(f"/api/vorgaenge/{vid}", headers=h, json={"status": "in_arbeit"})
    assert (await run_sla_eskalation())["eskalationen"] >= 1


@pytest.mark.asyncio
async def test_mandantentrennung_der_empfaenger(client, make_mandant, make_user, make_kunde):
    m1, a1, h1, v1 = await _aufbau(client, make_mandant, make_user, make_kunde)
    m2, a2, h2, v2 = await _aufbau(client, make_mandant, make_user, make_kunde)
    await _laeuft_seit(v1, 70)
    await run_sla_eskalation()
    async with system_session() as session:
        fremd = await session.scalar(
            select(func.count()).select_from(Notification).where(Notification.mandant_id == m2.id)
        )
    assert fremd == 0
    assert await _zaehle(Notification, m1.id) >= 1


@pytest.mark.asyncio
async def test_job_laeuft_viertelstuendlich(monkeypatch):
    aufrufe = []

    async def job():
        aufrufe.append(1)
        return {}

    monkeypatch.setattr(job_runner, "TAEGLICHE_JOBS", {})
    monkeypatch.setattr(job_runner, "SYSTEM_JOBS", {"v": (job, "viertelstuendlich")})
    basis = datetime(2026, 11, 3, 10, 0, 5, tzinfo=timezone.utc)
    await fuehre_tick(basis)
    await fuehre_tick(basis + timedelta(minutes=10))
    assert len(aufrufe) == 1
    await fuehre_tick(basis + timedelta(minutes=16))
    assert len(aufrufe) == 2


def test_sla_job_ist_registriert():
    assert "sla_eskalation" in job_runner.SYSTEM_JOBS
    assert job_runner.SYSTEM_JOBS["sla_eskalation"][1] == "viertelstuendlich"
