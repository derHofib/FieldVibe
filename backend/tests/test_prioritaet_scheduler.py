from datetime import datetime, timedelta, timezone

import pytest

from app.db.session import system_session
from app.models.dauerauftrag import Dauerauftrag
from app.models.vorgang import Vorgang
from app.services.scheduler_service import run_prioritaet_scheduler


async def _make_dauerauftrag(mandant, kunde, *, toleranz_frueh_tage=2, toleranz_spaet_tage=2) -> Dauerauftrag:
    async with system_session() as session:
        auftrag = Dauerauftrag(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            titel="Wöchentliche Wartung",
            abrechnungsart="wartungsvertrag",
            leistungstyp="wartung",
            intervall_tage=7,
            toleranz_frueh_tage=toleranz_frueh_tage,
            toleranz_spaet_tage=toleranz_spaet_tage,
        )
        session.add(auftrag)
        await session.flush()
        await session.refresh(auftrag)
        return auftrag


@pytest.mark.asyncio
async def test_prioritaet_scheduler_schreibt_faellige_dauerauftrag_vorgaenge_fort(
    make_mandant, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    auftrag = await _make_dauerauftrag(mandant, kunde)
    # Am Anlage-Tag mit Prio 1 erzeugt, aber inzwischen ueberfaellig --
    # der Lauf muss das nachziehen.
    vorgang = await make_vorgang(
        mandant=mandant,
        kunde=kunde,
        dauerauftrag_id=auftrag.id,
        prioritaet=1,
        faelligkeit_am=datetime.now(timezone.utc) - timedelta(days=3),
    )

    ergebnis = await run_prioritaet_scheduler([mandant.id])
    assert ergebnis["vorgaenge_aktualisiert"] == 1

    async with system_session() as session:
        refreshed = await session.get(Vorgang, vorgang.id)
        assert refreshed.prioritaet == 5


@pytest.mark.asyncio
async def test_prioritaet_scheduler_laesst_bereits_aktuelle_prioritaet_unangetastet(
    make_mandant, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    auftrag = await _make_dauerauftrag(mandant, kunde)
    await make_vorgang(
        mandant=mandant,
        kunde=kunde,
        dauerauftrag_id=auftrag.id,
        prioritaet=3,
        faelligkeit_am=datetime.now(timezone.utc),
    )

    ergebnis = await run_prioritaet_scheduler([mandant.id])
    assert ergebnis["vorgaenge_aktualisiert"] == 0


@pytest.mark.asyncio
async def test_prioritaet_scheduler_ruehrt_manuelle_vorgaenge_nicht_an(
    make_mandant, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(
        mandant=mandant,
        kunde=kunde,
        prioritaet=3,
        faelligkeit_am=datetime.now(timezone.utc) - timedelta(days=30),
    )

    ergebnis = await run_prioritaet_scheduler([mandant.id])
    assert ergebnis["vorgaenge_aktualisiert"] == 0

    async with system_session() as session:
        refreshed = await session.get(Vorgang, vorgang.id)
        assert refreshed.prioritaet == 3


@pytest.mark.asyncio
async def test_prioritaet_scheduler_ruehrt_abgeschlossene_dauerauftrag_vorgaenge_nicht_an(
    make_mandant, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    kunde = await make_kunde(mandant=mandant)
    auftrag = await _make_dauerauftrag(mandant, kunde)
    await make_vorgang(
        mandant=mandant,
        kunde=kunde,
        dauerauftrag_id=auftrag.id,
        status="abgeschlossen",
        prioritaet=1,
        faelligkeit_am=datetime.now(timezone.utc) - timedelta(days=30),
    )

    ergebnis = await run_prioritaet_scheduler([mandant.id])
    assert ergebnis["vorgaenge_aktualisiert"] == 0
