from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.db.session import system_session
from app.models.notification import Notification
from app.models.pruefmittel import Pruefmittel
from app.models.pruefzyklus import Pruefzyklus
from app.models.vorgang import Vorgang
from app.services.scheduler_service import run_pruefzyklen_scheduler
from tests.conftest import auth_headers, login


async def _make_pruefzyklus(mandant, anlage, *, faellig_in_tagen: int = 0) -> Pruefzyklus:
    async with system_session() as session:
        zyklus = Pruefzyklus(
            mandant_id=mandant.id,
            anlage_id=anlage.id,
            bezeichnung="E-Check",
            intervall_monate=12,
            naechste_pruefung_am=date.today() + timedelta(days=faellig_in_tagen),
        )
        session.add(zyklus)
        await session.flush()
        await session.refresh(zyklus)
        return zyklus


@pytest.mark.asyncio
async def test_scheduler_creates_vorgang_and_notifies_admins(
    make_mandant, make_user, make_kunde, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde)
    zyklus = await _make_pruefzyklus(mandant, anlage)

    ergebnis = await run_pruefzyklen_scheduler()
    assert ergebnis["vorgaenge_erstellt"] == 1

    async with system_session() as session:
        refreshed = await session.get(Pruefzyklus, zyklus.id)
        assert refreshed.offener_vorgang_id is not None

        vorgang = await session.get(Vorgang, refreshed.offener_vorgang_id)
        assert vorgang.leistungstyp == "pruefung"
        assert vorgang.anlage_id == anlage.id

        notifications = (
            await session.execute(
                select(Notification).where(Notification.user_id == admin.id)
            )
        ).scalars().all()
        assert len(notifications) == 1
        assert notifications[0].typ == "frist"


@pytest.mark.asyncio
async def test_scheduler_does_not_duplicate_open_vorgang_on_second_run(
    make_mandant, make_user, make_kunde, make_anlage
):
    mandant = await make_mandant()
    await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde)
    await _make_pruefzyklus(mandant, anlage)

    first = await run_pruefzyklen_scheduler()
    second = await run_pruefzyklen_scheduler()
    assert first["vorgaenge_erstellt"] == 1
    assert second["vorgaenge_erstellt"] == 0


@pytest.mark.asyncio
async def test_completing_linked_vorgang_advances_pruefzyklus(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde)
    zyklus = await _make_pruefzyklus(mandant, anlage)

    await run_pruefzyklen_scheduler()
    async with system_session() as session:
        refreshed = await session.get(Pruefzyklus, zyklus.id)
        vorgang_id = refreshed.offener_vorgang_id
        alte_naechste_pruefung = refreshed.naechste_pruefung_am

    token = await login(client, admin.email, "pw-123456")
    resp = await client.patch(
        f"/api/vorgaenge/{vorgang_id}", headers=auth_headers(token), json={"status": "abgeschlossen"}
    )
    assert resp.status_code == 200

    async with system_session() as session:
        refreshed = await session.get(Pruefzyklus, zyklus.id)
        assert refreshed.offener_vorgang_id is None
        assert refreshed.letzte_pruefung_am == date.today()
        assert refreshed.naechste_pruefung_am > alte_naechste_pruefung

    # Naechster Lauf legt fuer denselben (jetzt fortgeschriebenen) Zyklus
    # keinen neuen Vorgang an, da die neue Faelligkeit weit in der Zukunft liegt.
    ergebnis = await run_pruefzyklen_scheduler()
    assert ergebnis["vorgaenge_erstellt"] == 0


@pytest.mark.asyncio
async def test_scheduler_notifies_for_due_pruefmittel_without_duplicate(
    make_mandant, make_user
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")

    async with system_session() as session:
        mittel = Pruefmittel(
            mandant_id=mandant.id,
            bezeichnung="Multimeter",
            kalibrierintervall_monate=12,
            naechste_kalibrierung_am=date.today(),
        )
        session.add(mittel)
        await session.flush()

    first = await run_pruefzyklen_scheduler()
    second = await run_pruefzyklen_scheduler()
    assert first["pruefmittel_faellig"] == 1
    assert second["pruefmittel_faellig"] == 1  # weiterhin "faellig" gezaehlt

    async with system_session() as session:
        notifications = (
            await session.execute(
                select(Notification).where(
                    Notification.user_id == admin.id, Notification.ref_entity_type == "pruefmittel"
                )
            )
        ).scalars().all()
        # trotz zwei Laeufen nur eine ungelesene Erinnerung, kein Spam
        assert len(notifications) == 1
