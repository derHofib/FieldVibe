from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.session import system_session
from app.models.notification import Notification
from app.models.vorgang import Vorgang
from app.services.scheduler_service import run_wiedervorlage_scheduler
from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_wartet_kunde_setzt_wiedervorlage_mit_globalem_default(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}",
        headers=auth_headers(token),
        json={"status": "wartet_kunde"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["wiedervorlage_am"] is not None
    erwartet = datetime.now(timezone.utc) + timedelta(days=14)
    tatsaechlich = datetime.fromisoformat(body["wiedervorlage_am"])
    assert abs((tatsaechlich - erwartet).total_seconds()) < 60


@pytest.mark.asyncio
async def test_wartet_kunde_mit_eigener_frist_ueberschreibt_default(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}",
        headers=auth_headers(token),
        json={"status": "wartet_kunde", "wiedervorlage_tage": 3},
    )
    assert resp.status_code == 200
    erwartet = datetime.now(timezone.utc) + timedelta(days=3)
    tatsaechlich = datetime.fromisoformat(resp.json()["wiedervorlage_am"])
    assert abs((tatsaechlich - erwartet).total_seconds()) < 60


@pytest.mark.asyncio
async def test_wartet_kunde_verwendet_mandanten_eigenen_default(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    settings_resp = await client.patch(
        "/api/mandant/einstellungen",
        headers=auth_headers(token),
        json={"wiedervorlage_standard_tage": 5},
    )
    assert settings_resp.status_code == 200
    assert settings_resp.json()["effektive_wiedervorlage_standard_tage"] == 5

    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}",
        headers=auth_headers(token),
        json={"status": "wartet_kunde"},
    )
    erwartet = datetime.now(timezone.utc) + timedelta(days=5)
    tatsaechlich = datetime.fromisoformat(resp.json()["wiedervorlage_am"])
    assert abs((tatsaechlich - erwartet).total_seconds()) < 60


@pytest.mark.asyncio
async def test_wiedervorlage_tage_ohne_wartet_kunde_abgelehnt(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}",
        headers=auth_headers(token),
        json={"wiedervorlage_tage": 5},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_wiedervorlage_wird_beim_verlassen_von_wartet_kunde_geleert(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    await client.patch(
        f"/api/vorgaenge/{vorgang.id}",
        headers=auth_headers(token),
        json={"status": "wartet_kunde"},
    )
    resp = await client.patch(
        f"/api/vorgaenge/{vorgang.id}",
        headers=auth_headers(token),
        json={"status": "in_arbeit"},
    )
    assert resp.status_code == 200
    assert resp.json()["wiedervorlage_am"] is None


@pytest.mark.asyncio
async def test_wiedervorlage_scheduler_benachrichtigt_zugewiesenen_user(
    make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(
        mandant=mandant,
        kunde=kunde,
        status="wartet_kunde",
        zugewiesener_user_id=techniker.id,
        wiedervorlage_am=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    ergebnis = await run_wiedervorlage_scheduler()
    assert ergebnis["vorgaenge_benachrichtigt"] == 1

    async with system_session() as session:
        refreshed = await session.get(Vorgang, vorgang.id)
        assert refreshed.wiedervorlage_am is None

        notifications = (
            await session.execute(
                select(Notification).where(Notification.user_id == techniker.id)
            )
        ).scalars().all()
        assert len(notifications) == 1
        assert notifications[0].typ == "frist"


@pytest.mark.asyncio
async def test_wiedervorlage_scheduler_faellt_ohne_zuweisung_auf_admin_zurueck(
    make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant)
    await make_vorgang(
        mandant=mandant,
        kunde=kunde,
        status="wartet_kunde",
        wiedervorlage_am=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    ergebnis = await run_wiedervorlage_scheduler()
    assert ergebnis["vorgaenge_benachrichtigt"] == 1

    async with system_session() as session:
        notifications = (
            await session.execute(select(Notification).where(Notification.user_id == admin.id))
        ).scalars().all()
        assert len(notifications) == 1


@pytest.mark.asyncio
async def test_wiedervorlage_scheduler_ignoriert_noch_nicht_faellige(
    make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant)
    await make_vorgang(
        mandant=mandant,
        kunde=kunde,
        status="wartet_kunde",
        wiedervorlage_am=datetime.now(timezone.utc) + timedelta(days=5),
    )

    ergebnis = await run_wiedervorlage_scheduler()
    assert ergebnis["vorgaenge_benachrichtigt"] == 0
