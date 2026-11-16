"""Worker-Jobs laufen je Mandant in einer Mandanten-Session (RLS), nicht in einer
RLS-umgehenden system_session; ein defekter Mandant stoppt die uebrigen nicht."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.db.session import system_session
from app.services import job_runner, mandanten_lauf
from app.services.job_runner import fuehre_tick
from app.services.job_state_service import lade_laeufe
from app.services.mandanten_lauf import je_mandant
from app.services.scheduler_service import run_prioritaet_scheduler


@pytest.fixture
def tenant_spion(monkeypatch):
    """Protokolliert (mandant_id, is_super_admin) jeder in mandanten_lauf geoeffneten Session."""
    geoeffnet: list[tuple] = []
    echt = mandanten_lauf.tenant_session

    def _spion(*, mandant_id, is_super_admin):
        geoeffnet.append((mandant_id, is_super_admin))
        return echt(mandant_id=mandant_id, is_super_admin=is_super_admin)

    monkeypatch.setattr(mandanten_lauf, "tenant_session", _spion)
    return geoeffnet


async def test_job_fehler_bei_mandant_a_stoppt_mandant_b_nicht(make_mandant, monkeypatch):
    a = await make_mandant("A")
    b = await make_mandant("B")
    verarbeitet: list = []

    async def job(mandant_ids):
        async def arbeit(session, mandant_id):
            verarbeitet.append(mandant_id)
            if mandant_id == a.id:
                raise RuntimeError("kaputt")
            return {"n": 1}

        return await je_mandant(mandant_ids, arbeit)

    monkeypatch.setattr(job_runner, "TAEGLICHE_JOBS", {"demo": job})
    monkeypatch.setattr(job_runner, "SYSTEM_JOBS", {})

    await fuehre_tick(datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc))

    assert {a.id, b.id} <= set(verarbeitet)
    async with system_session(grund="test") as session:
        laeufe = await lade_laeufe(session, "demo")
    assert laeufe[b.id].letzter_lauf_am is not None and laeufe[b.id].fehler_in_folge == 0
    assert laeufe[a.id].letzter_lauf_am is None
    assert laeufe[a.id].fehler_in_folge == 1 and "RuntimeError" in laeufe[a.id].letzter_fehler


async def test_je_mandant_wirft_erst_nach_allen_mandanten(make_mandant):
    a = await make_mandant("A")
    b = await make_mandant("B")
    verarbeitet: list = []

    async def arbeit(session, mandant_id):
        verarbeitet.append(mandant_id)
        if mandant_id == a.id:
            raise RuntimeError("kaputt")
        return {"n": 1}

    with pytest.raises(RuntimeError):
        await je_mandant([a.id, b.id], arbeit)
    assert verarbeitet == [a.id, b.id]


async def test_arbeit_laeuft_unter_dem_mandantenkontext(make_mandant, tenant_spion):
    a = await make_mandant("A")
    b = await make_mandant("B")
    await make_mandant("Pausiert", status="pausiert")
    gesehen: dict = {}

    async def arbeit(session, mandant_id):
        gesehen[mandant_id] = (
            (await session.execute(text("SELECT current_setting('app.current_mandant', true)"))).scalar_one(),
            (await session.execute(text("SELECT current_setting('app.is_super_admin', true)"))).scalar_one(),
        )
        return {"n": 1}

    ergebnis = await je_mandant(None, arbeit)

    assert ergebnis == {"n": 2}
    assert gesehen == {a.id: (str(a.id), "false"), b.id: (str(b.id), "false")}
    assert sorted(tenant_spion, key=str) == sorted([(a.id, False), (b.id, False)], key=str)


async def test_scheduler_oeffnet_je_mandant_eine_mandanten_session(make_mandant, tenant_spion):
    a = await make_mandant("A")
    b = await make_mandant("B")

    ergebnis = await run_prioritaet_scheduler([a.id, b.id])

    assert ergebnis == {"vorgaenge_aktualisiert": 0}
    assert tenant_spion == [(a.id, False), (b.id, False)]
