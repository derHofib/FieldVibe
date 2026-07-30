from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.db.session import system_session
from app.models.inventurzyklus import InventurZyklus
from app.models.notification import Notification
from app.services.scheduler_service import run_pruefzyklen_scheduler
from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_create_inventurzyklus_ohne_naechste_faelligkeit_defaults(
    client, make_mandant, make_user, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/inventurzyklen",
        headers=auth_headers(token),
        json={"lager_id": str(fahrzeug.id), "intervall_tage": 90},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["letzte_inventur_am"] is None
    assert body["naechste_inventur_am"] == (date.today() + timedelta(days=90)).isoformat()
    assert body["aktiv"] is True


@pytest.mark.asyncio
async def test_kundenanlage_ist_kein_gueltiger_lagerort(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    kundenanlage = await make_anlage(mandant=mandant, kunde=kunde)
    token = await login(client, admin.email, "pw-123456")

    resp = await client.post(
        "/api/inventurzyklen",
        headers=auth_headers(token),
        json={"lager_id": str(kundenanlage.id), "intervall_tage": 90},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_zweiter_zyklus_fuer_denselben_lagerort_schlaegt_fehl(
    client, make_mandant, make_user, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter")
    token = await login(client, admin.email, "pw-123456")

    await client.post(
        "/api/inventurzyklen",
        headers=auth_headers(token),
        json={"lager_id": str(fahrzeug.id), "intervall_tage": 90},
    )
    resp = await client.post(
        "/api/inventurzyklen",
        headers=auth_headers(token),
        json={"lager_id": str(fahrzeug.id), "intervall_tage": 30},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_techniker_darf_keinen_zyklus_anlegen(client, make_mandant, make_user, make_anlage):
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter")
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.post(
        "/api/inventurzyklen",
        headers=auth_headers(token),
        json={"lager_id": str(fahrzeug.id), "intervall_tage": 90},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_inventur_durchgefuehrt_schreibt_naechste_faelligkeit_fort(
    client, make_mandant, make_user, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter")
    token = await login(client, admin.email, "pw-123456")

    create_resp = await client.post(
        "/api/inventurzyklen",
        headers=auth_headers(token),
        json={"lager_id": str(fahrzeug.id), "intervall_tage": 30},
    )
    zyklus_id = create_resp.json()["id"]

    heute = date.today()
    update_resp = await client.patch(
        f"/api/inventurzyklen/{zyklus_id}",
        headers=auth_headers(token),
        json={"letzte_inventur_am": heute.isoformat()},
    )
    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["letzte_inventur_am"] == heute.isoformat()
    assert body["naechste_inventur_am"] == (heute + timedelta(days=30)).isoformat()


@pytest.mark.asyncio
async def test_aktiv_false_pausiert_zyklus(client, make_mandant, make_user, make_anlage):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter")
    token = await login(client, admin.email, "pw-123456")

    create_resp = await client.post(
        "/api/inventurzyklen",
        headers=auth_headers(token),
        json={
            "lager_id": str(fahrzeug.id),
            "intervall_tage": 30,
            "naechste_inventur_am": date.today().isoformat(),
        },
    )
    zyklus_id = create_resp.json()["id"]

    pause_resp = await client.patch(
        f"/api/inventurzyklen/{zyklus_id}", headers=auth_headers(token), json={"aktiv": False}
    )
    assert pause_resp.status_code == 200
    assert pause_resp.json()["aktiv"] is False

    stories_resp = await client.get("/api/stories", headers=auth_headers(token))
    inventur_items = [f for f in stories_resp.json()["fristen"] if "Inventur" in f["titel"]]
    assert inventur_items == []


@pytest.mark.asyncio
async def test_faelliger_zyklus_erscheint_in_fristen(client, make_mandant, make_user, make_anlage):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter")
    token = await login(client, admin.email, "pw-123456")

    await client.post(
        "/api/inventurzyklen",
        headers=auth_headers(token),
        json={
            "lager_id": str(fahrzeug.id),
            "intervall_tage": 30,
            "naechste_inventur_am": date.today().isoformat(),
        },
    )

    resp = await client.get("/api/stories", headers=auth_headers(token))
    inventur_items = [f for f in resp.json()["fristen"] if f["titel"] == "Inventur: Transporter"]
    assert len(inventur_items) == 1
    assert inventur_items[0]["ziel_typ"] == "anlage"
    assert inventur_items[0]["ziel_id"] == str(fahrzeug.id)


async def _make_inventurzyklus(mandant, lager, *, faellig_in_tagen: int = 0) -> InventurZyklus:
    async with system_session() as session:
        zyklus = InventurZyklus(
            mandant_id=mandant.id,
            lager_id=lager.id,
            intervall_tage=90,
            naechste_inventur_am=date.today() + timedelta(days=faellig_in_tagen),
        )
        session.add(zyklus)
        await session.flush()
        await session.refresh(zyklus)
        return zyklus


@pytest.mark.asyncio
async def test_scheduler_benachrichtigt_admins_ohne_vorgang_zu_erzeugen(
    make_mandant, make_user, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter")
    await _make_inventurzyklus(mandant, fahrzeug)

    ergebnis = await run_pruefzyklen_scheduler()
    assert ergebnis["inventurzyklen_faellig"] == 1
    assert ergebnis["vorgaenge_erstellt"] == 0

    async with system_session() as session:
        notifications = (
            await session.execute(select(Notification).where(Notification.user_id == admin.id))
        ).scalars().all()
        assert len(notifications) == 1
        assert notifications[0].ref_entity_type == "anlage"
        assert notifications[0].ref_entity_id == fahrzeug.id


@pytest.mark.asyncio
async def test_scheduler_benachrichtigt_zugewiesenen_techniker(
    client, make_mandant, make_user, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter")
    await _make_inventurzyklus(mandant, fahrzeug)

    admin_token = await login(client, admin.email, "pw-123456")
    await client.put(
        f"/api/fahrzeug-zuweisungen/{techniker.id}",
        headers=auth_headers(admin_token),
        json={"anlage_id": str(fahrzeug.id)},
    )

    await run_pruefzyklen_scheduler()

    async with system_session() as session:
        notifications = (
            await session.execute(select(Notification).where(Notification.user_id == techniker.id))
        ).scalars().all()
        assert len(notifications) == 1


@pytest.mark.asyncio
async def test_scheduler_dedupliziert_ungelesene_erinnerung(make_mandant, make_user, make_anlage):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter")
    await _make_inventurzyklus(mandant, fahrzeug)

    await run_pruefzyklen_scheduler()
    await run_pruefzyklen_scheduler()

    async with system_session() as session:
        notifications = (
            await session.execute(select(Notification).where(Notification.user_id == admin.id))
        ).scalars().all()
        assert len(notifications) == 1


@pytest.mark.asyncio
async def test_scheduler_ignoriert_pausierten_zyklus(make_mandant, make_user, make_anlage):
    mandant = await make_mandant()
    await make_user(mandant=mandant, role="mandant_admin")
    fahrzeug = await make_anlage(mandant=mandant, objekttyp="fahrzeug", bezeichnung="Transporter")
    zyklus = await _make_inventurzyklus(mandant, fahrzeug)
    async with system_session() as session:
        db_zyklus = await session.get(InventurZyklus, zyklus.id)
        db_zyklus.aktiv = False
        await session.flush()

    ergebnis = await run_pruefzyklen_scheduler()
    assert ergebnis["inventurzyklen_faellig"] == 0
