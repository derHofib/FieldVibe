"""Zustandsgefuehrte Jobs mit simulierter Uhr (app/services/job_runner.py)."""
import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.db.session import system_session
from app.models.dauerauftrag_ziel import DauerauftragZiel
from app.models.job_lauf import JobLauf
from app.models.mandant import Mandant
from app.models.vorgang import Vorgang
from app.services import job_runner
from app.services.job_runner import fuehre_tick, ist_faellig, letzter_slot
from app.services.job_state_service import lade_laeufe, markiere_lauf
from app.services.scheduler_service import run_dauerauftraege_scheduler
from tests.test_dauerauftraege import _make_dauerauftrag_mit_ziel


def utc(tag: int, stunde: int, minute: int = 0, sekunde: int = 0) -> datetime:
    return datetime(2026, 3, tag, stunde, minute, sekunde, tzinfo=timezone.utc)


class Fake:
    """Ersatz-Job: merkt sich Aufrufe, kann scheitern oder trödeln."""

    def __init__(self, scheitert_bei=(), dauer=0.0):
        self.aufrufe: list[list] = []
        self.scheitert_bei = set(scheitert_bei)
        self.dauer = dauer

    async def __call__(self, mandant_ids):
        self.aufrufe.append(list(mandant_ids))
        if self.dauer:
            await asyncio.sleep(self.dauer)
        if self.scheitert_bei & set(mandant_ids):
            raise RuntimeError("kaputt")
        return {"n": len(mandant_ids)}


@pytest.fixture
def nur_job(monkeypatch):
    def _setze(fake: Fake, name="demo"):
        monkeypatch.setattr(job_runner, "TAEGLICHE_JOBS", {name: fake})
        monkeypatch.setattr(job_runner, "SYSTEM_JOBS", {})
        return fake

    return _setze


async def _stunde_setzen(mandant, stunde: int | None):
    async with system_session() as session:
        await session.execute(update(Mandant).where(Mandant.id == mandant.id).values(scheduler_stunde_utc=stunde))


async def _lauf(job: str, mandant) -> JobLauf | None:
    async with system_session() as session:
        return (await lade_laeufe(session, job)).get(mandant.id if mandant else None)


def test_letzter_slot_vor_und_nach_der_stunde():
    assert letzter_slot(utc(10, 2, 59), 3) == utc(9, 3)
    assert letzter_slot(utc(10, 3, 0), 3) == utc(10, 3)
    assert letzter_slot(utc(10, 23, 59), 3) == utc(10, 3)
    assert letzter_slot(utc(10, 12, 0, 0), 12) == utc(10, 12)


def test_ist_faellig_regeln():
    slot = utc(10, 3)
    erfolgreich = JobLauf(job="x", letzter_lauf_am=utc(10, 3, 5), letzter_versuch_am=utc(10, 3, 5), fehler_in_folge=0)
    assert not ist_faellig(erfolgreich, slot, utc(10, 9), 30)
    assert ist_faellig(erfolgreich, utc(11, 3), utc(11, 3, 1), 30)
    assert ist_faellig(None, slot, utc(10, 9), 30)
    gescheitert = JobLauf(job="x", letzter_lauf_am=utc(9, 3), letzter_versuch_am=utc(10, 8, 50), fehler_in_folge=2)
    assert not ist_faellig(gescheitert, slot, utc(10, 9, 0), 30)
    assert ist_faellig(gescheitert, slot, utc(10, 9, 21), 30)


async def test_neustart_um_zwoelf_uhr_genau_fuehrt_den_lauf_aus(make_mandant, nur_job):
    mandant = await make_mandant()
    await _stunde_setzen(mandant, 12)
    fake = nur_job(Fake())

    await fuehre_tick(utc(10, 12, 0, 0))
    assert fake.aufrufe == [[mandant.id]]
    # Weitere Ticks und ein erneuter Neustart in derselben Stunde laufen nicht doppelt.
    await fuehre_tick(utc(10, 12, 0, 30))
    await fuehre_tick(utc(10, 12, 45))
    assert len(fake.aufrufe) == 1
    # Naechster Tag: erst ab 12:00 faellig, nicht vorher.
    await fuehre_tick(utc(11, 11, 59))
    assert len(fake.aufrufe) == 1
    await fuehre_tick(utc(11, 12, 0))
    assert len(fake.aufrufe) == 2


async def test_neustart_kurz_nach_der_stunde_holt_den_lauf_nach(make_mandant, nur_job):
    """Frueher: Worker um 12:00:01 gestartet, Tick erst um 13:00 -> Lauf des Tages verloren."""
    mandant = await make_mandant()
    await _stunde_setzen(mandant, 12)
    fake = nur_job(Fake())
    await markiere_lauf_system(mandant, "demo", utc(9, 12, 0, 5))

    await fuehre_tick(utc(10, 12, 0, 1))
    assert fake.aufrufe == [[mandant.id]]


async def markiere_lauf_system(mandant, job, zeitpunkt):
    async with system_session() as session:
        await markiere_lauf(session, job, mandant.id, erfolg=True, jetzt=zeitpunkt)


async def test_ausfall_ueber_zwei_tage_wird_einmal_nachgeholt(make_mandant, nur_job, caplog):
    mandant = await make_mandant()
    await _stunde_setzen(mandant, 3)
    fake = nur_job(Fake())
    await markiere_lauf_system(mandant, "demo", utc(1, 3, 0, 10))
    caplog.set_level(logging.INFO, logger="app.worker")

    await fuehre_tick(utc(3, 10, 0))
    assert fake.aufrufe == [[mandant.id]], "genau EIN Nachhol-Lauf, nicht einer je verpasstem Tag"
    assert any("holt einen versaeumten Lauf nach" in r.getMessage() for r in caplog.records)
    assert not any(r.levelno >= logging.ERROR for r in caplog.records)
    await fuehre_tick(utc(3, 10, 1))
    assert len(fake.aufrufe) == 1


async def test_ausfall_ueber_der_obergrenze_wird_als_error_gemeldet_und_trotzdem_nachgeholt(
    make_mandant, nur_job, caplog
):
    mandant = await make_mandant()
    fake = nur_job(Fake())
    await markiere_lauf_system(mandant, "demo", utc(1, 3, 0, 10))
    caplog.set_level(logging.INFO, logger="app.worker")

    await fuehre_tick(utc(9, 10, 0))
    assert len(fake.aufrufe) == 1
    fehler = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert fehler and getattr(fehler[0], "event", None) == "job_nachholen_ueberschritten"


async def test_zwei_gleichzeitige_ticks_fuehren_den_job_nur_einmal_aus(make_mandant, nur_job):
    mandant = await make_mandant()
    fake = nur_job(Fake(dauer=0.4))

    a, b = await asyncio.gather(fuehre_tick(utc(10, 10, 0)), fuehre_tick(utc(10, 10, 0)))
    assert len(fake.aufrufe) == 1
    assert sorted([a["lock"], b["lock"]]) == [False, True]
    assert (await _lauf("demo", mandant)).letzter_lauf_am is not None


async def test_fehler_wird_nach_pause_wiederholt_nicht_bei_jedem_tick(make_mandant, nur_job):
    mandant = await make_mandant()
    fake = nur_job(Fake(scheitert_bei={mandant.id}))

    await fuehre_tick(utc(10, 10, 0))
    lauf = await _lauf("demo", mandant)
    assert lauf.fehler_in_folge == 1 and "RuntimeError" in lauf.letzter_fehler and lauf.letzter_lauf_am is None

    await fuehre_tick(utc(10, 10, 10))
    assert len(fake.aufrufe) == 1, "innerhalb der Retry-Pause kein neuer Versuch"

    fake.scheitert_bei = set()
    await fuehre_tick(utc(10, 10, 31))
    assert len(fake.aufrufe) == 2
    lauf = await _lauf("demo", mandant)
    assert lauf.fehler_in_folge == 0 and lauf.letzter_fehler is None and lauf.letzter_lauf_am is not None


async def test_defekter_mandant_blockiert_die_uebrigen_nicht(make_mandant, nur_job):
    gut = await make_mandant("Gut")
    kaputt = await make_mandant("Kaputt")
    fake = nur_job(Fake(scheitert_bei={kaputt.id}))

    await fuehre_tick(utc(10, 10, 0))
    assert set(fake.aufrufe[0]) == {gut.id, kaputt.id}
    assert (await _lauf("demo", gut)).letzter_lauf_am is not None
    assert (await _lauf("demo", kaputt)).fehler_in_folge == 1

    # Naechster Versuch nach der Pause betrifft nur noch den defekten Mandanten.
    await fuehre_tick(utc(10, 10, 31))
    assert fake.aufrufe[-1] == [kaputt.id]


async def test_inaktive_mandanten_und_eigene_stunde(make_mandant, nur_job):
    aktiv = await make_mandant("Aktiv")
    pausiert = await make_mandant("Pausiert", status="pausiert")
    fake = nur_job(Fake())

    await fuehre_tick(utc(10, 10, 0))
    assert fake.aufrufe == [[aktiv.id]]
    assert await _lauf("demo", pausiert) is None


async def test_systemjobs_stuendlich_und_taeglich(nur_job, monkeypatch):
    nur_job(Fake())
    stuendlich, taeglich = Fake(), Fake()

    async def s():
        stuendlich.aufrufe.append([])
        return {"a": 1}

    async def t():
        taeglich.aufrufe.append([])
        return {"b": 2}

    monkeypatch.setattr(job_runner, "SYSTEM_JOBS", {"s": (s, "stuendlich"), "t": (t, "taeglich")})
    await fuehre_tick(utc(10, 10, 5))
    await fuehre_tick(utc(10, 10, 40))
    assert len(stuendlich.aufrufe) == 1 and len(taeglich.aufrufe) == 1
    await fuehre_tick(utc(10, 11, 1))
    assert len(stuendlich.aufrufe) == 2 and len(taeglich.aufrufe) == 1
    await fuehre_tick(utc(11, 3, 1))
    assert len(taeglich.aufrufe) == 2


async def test_systemjob_fehler_wird_festgehalten_und_blockiert_andere_nicht(nur_job, monkeypatch):
    nur_job(Fake())
    gesund = Fake()

    async def kaputt():
        raise ValueError("boom")

    async def ok():
        gesund.aufrufe.append([])

    monkeypatch.setattr(job_runner, "SYSTEM_JOBS", {"kaputt": (kaputt, "stuendlich"), "ok": (ok, "stuendlich")})
    await fuehre_tick(utc(10, 10, 5))
    assert len(gesund.aufrufe) == 1
    lauf = await _lauf("kaputt", None)
    assert lauf.fehler_in_folge == 1 and "ValueError" in lauf.letzter_fehler


# --- Idempotenz der echten Jobs --------------------------------------------------


async def test_dauerauftrag_nach_ausfall_und_doppeltem_tick_nur_ein_vorgang(make_mandant, make_kunde, monkeypatch):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    auftrag, ziel = await _make_dauerauftrag_mit_ziel(
        mandant=mandant, kunde=kunde, naechste_faelligkeit_am=date.today() - timedelta(days=2)
    )
    monkeypatch.setattr(job_runner, "SYSTEM_JOBS", {})
    monkeypatch.setattr(job_runner, "TAEGLICHE_JOBS", {"dauerauftraege": job_runner.run_dauerauftraege_scheduler})
    jetzt = datetime.now(timezone.utc)

    await asyncio.gather(fuehre_tick(jetzt), fuehre_tick(jetzt))
    await fuehre_tick(jetzt + timedelta(minutes=1))
    await run_dauerauftraege_scheduler([mandant.id])

    async with system_session() as session:
        anzahl = len((await session.execute(select(Vorgang).where(Vorgang.dauerauftrag_id == auftrag.id))).scalars().all())
    assert anzahl == 1


async def test_dauerauftrag_zeile_in_bearbeitung_wird_uebersprungen_nicht_doppelt_erzeugt(make_mandant, make_kunde):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    auftrag, ziel = await _make_dauerauftrag_mit_ziel(
        mandant=mandant, kunde=kunde, naechste_faelligkeit_am=date.today() - timedelta(days=1)
    )
    # Ein zweiter Prozess hat die Zeile gerade pausiert (FOR UPDATE).
    async with system_session() as sperre:
        await sperre.execute(select(DauerauftragZiel).where(DauerauftragZiel.id == ziel.id).with_for_update())
        waehrend = await run_dauerauftraege_scheduler([mandant.id])
        assert waehrend["vorgaenge_erstellt"] == 0
    danach = await run_dauerauftraege_scheduler([mandant.id])
    assert danach["vorgaenge_erstellt"] == 1
