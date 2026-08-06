import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.session import system_session
from app.models.eingangsrechnung import Eingangsrechnung, EingangsrechnungZahlung
from app.models.notification import Notification
from app.services.kreditorenbuchhaltung_service import run_kreditoren_faelligkeits_check


async def _make_eingangsrechnung(mandant, ersteller, *, faellig_in_tagen=None, skonto_prozent=None, skonto_tage=None, betrag_netto="100.00"):
    async with system_session() as session:
        eingangsrechnung = Eingangsrechnung(
            mandant_id=mandant.id,
            lieferant_name="Sonepar",
            rechnungsnummer_lieferant=f"RE-{uuid.uuid4().hex[:8]}",
            rechnungsdatum=date.today(),
            betrag_netto=Decimal(betrag_netto),
            skonto_prozent=Decimal(skonto_prozent) if skonto_prozent is not None else None,
            skonto_tage=skonto_tage,
            erstellt_von=ersteller.id,
            faellig_am=(date.today() + timedelta(days=faellig_in_tagen)) if faellig_in_tagen is not None else None,
        )
        session.add(eingangsrechnung)
        await session.flush()
        await session.refresh(eingangsrechnung)
        return eingangsrechnung


@pytest.mark.asyncio
async def test_faelligkeits_erinnerung_wird_erstellt(make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    eingangsrechnung = await _make_eingangsrechnung(mandant, admin, faellig_in_tagen=2)

    ergebnis = await run_kreditoren_faelligkeits_check()
    assert ergebnis["faelligkeit_erinnerungen"] == 1

    async with system_session() as session:
        notifications = (
            await session.execute(select(Notification).where(Notification.user_id == admin.id))
        ).scalars().all()
        assert any(n.ref_entity_id == eingangsrechnung.id for n in notifications)


@pytest.mark.asyncio
async def test_keine_erinnerung_wenn_faellig_am_zu_weit_entfernt(make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    await _make_eingangsrechnung(mandant, admin, faellig_in_tagen=10)

    ergebnis = await run_kreditoren_faelligkeits_check()
    assert ergebnis["faelligkeit_erinnerungen"] == 0


@pytest.mark.asyncio
async def test_ueberfaellige_rechnung_erinnert_ebenfalls(make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    await _make_eingangsrechnung(mandant, admin, faellig_in_tagen=-5)

    ergebnis = await run_kreditoren_faelligkeits_check()
    assert ergebnis["faelligkeit_erinnerungen"] == 1


@pytest.mark.asyncio
async def test_wiederholter_lauf_dedupliziert(make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    await _make_eingangsrechnung(mandant, admin, faellig_in_tagen=1)

    erster = await run_kreditoren_faelligkeits_check()
    assert erster["faelligkeit_erinnerungen"] == 1

    zweiter = await run_kreditoren_faelligkeits_check()
    assert zweiter["faelligkeit_erinnerungen"] == 0


@pytest.mark.asyncio
async def test_skonto_erinnerung_wird_erstellt(make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    eingangsrechnung = await _make_eingangsrechnung(
        mandant, admin, skonto_prozent="2.00", skonto_tage=1
    )

    ergebnis = await run_kreditoren_faelligkeits_check()
    assert ergebnis["skonto_erinnerungen"] == 1

    async with system_session() as session:
        notifications = (
            await session.execute(
                select(Notification).where(
                    Notification.ref_entity_type == "eingangsrechnung_skonto",
                    Notification.ref_entity_id == eingangsrechnung.id,
                )
            )
        ).scalars().all()
        assert len(notifications) == 1
        assert "Skonto" in notifications[0].titel


@pytest.mark.asyncio
async def test_skonto_erinnerung_entfaellt_bei_bereits_voller_bezahlung(make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    eingangsrechnung = await _make_eingangsrechnung(
        mandant, admin, skonto_prozent="2.00", skonto_tage=1, betrag_netto="100.00"
    )
    async with system_session() as session:
        session.add(
            EingangsrechnungZahlung(
                mandant_id=mandant.id,
                eingangsrechnung_id=eingangsrechnung.id,
                betrag=Decimal("119.00"),
                erstellt_von=admin.id,
            )
        )
        await session.flush()

    ergebnis = await run_kreditoren_faelligkeits_check()
    assert ergebnis["skonto_erinnerungen"] == 0


@pytest.mark.asyncio
async def test_mahnwesen_scoped_to_mandant_ids_ignores_others(make_mandant, make_user):
    mandant1 = await make_mandant(name="Betrieb1")
    mandant2 = await make_mandant(name="Betrieb2")
    admin1 = await make_user(mandant=mandant1, role="mandant_admin")
    admin2 = await make_user(mandant=mandant2, role="mandant_admin")
    await _make_eingangsrechnung(mandant1, admin1, faellig_in_tagen=1)
    await _make_eingangsrechnung(mandant2, admin2, faellig_in_tagen=1)

    ergebnis = await run_kreditoren_faelligkeits_check(mandant_ids=[mandant1.id])
    assert ergebnis["faelligkeit_erinnerungen"] == 1
