from datetime import date, datetime, timedelta, timezone

import pytest

from app.db.session import system_session
from app.models.pruefmittel import Pruefmittel
from app.models.pruefzyklus import Pruefzyklus
from app.models.termin import Termin
from app.models.vorgang import Vorgang
from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_stories_empty_groups_are_typed_arrays(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    await make_vorgang(mandant=mandant, kunde=kunde, status="neu")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/stories", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["heute"] == []
    assert body["fristen"] == []
    assert body["material"] == []
    assert body["wartet_kunde"] == []  # zu frisch, noch keine 3 Tage alt


@pytest.mark.asyncio
async def test_wartet_kunde_appears_after_threshold(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, status="wartet_kunde")

    async with system_session() as session:
        db_vorgang = await session.get(Vorgang, vorgang.id)
        db_vorgang.last_activity_at = datetime.now(timezone.utc) - timedelta(days=5)
        await session.flush()

    token = await login(client, admin.email, "pw-123456")
    resp = await client.get("/api/stories", headers=auth_headers(token))
    assert resp.status_code == 200
    wartet = resp.json()["wartet_kunde"]
    assert len(wartet) == 1
    assert wartet[0]["ziel_id"] == str(vorgang.id)
    assert wartet[0]["ampel"] == "rot"


@pytest.mark.asyncio
async def test_heute_shows_own_termine_only(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    tech1 = await make_user(mandant=mandant, role="techniker", password="pw-123456", name="T1")
    tech2 = await make_user(mandant=mandant, role="techniker", password="pw-123456", name="T2")
    kunde = await make_kunde(mandant=mandant)
    vorgang1 = await make_vorgang(mandant=mandant, kunde=kunde, titel="V1")
    vorgang2 = await make_vorgang(mandant=mandant, kunde=kunde, titel="V2")

    now = datetime.now(timezone.utc)
    async with system_session() as session:
        session.add(
            Termin(
                mandant_id=mandant.id,
                vorgang_id=vorgang1.id,
                techniker_id=tech1.id,
                erstellt_von=tech1.id,
                titel="Mein Termin heute",
                start_at=now + timedelta(hours=1),
                ende_at=now + timedelta(hours=2),
            )
        )
        session.add(
            Termin(
                mandant_id=mandant.id,
                vorgang_id=vorgang2.id,
                techniker_id=tech2.id,
                erstellt_von=tech2.id,
                titel="Termin von T2",
                start_at=now + timedelta(hours=1),
                ende_at=now + timedelta(hours=2),
            )
        )

    token = await login(client, tech1.email, "pw-123456")
    resp = await client.get("/api/stories", headers=auth_headers(token))
    heute = resp.json()["heute"]
    assert len(heute) == 1
    assert heute[0]["titel"] == "Mein Termin heute"
    assert heute[0]["ziel_id"] == str(vorgang1.id)


@pytest.mark.asyncio
async def test_fristen_include_pruefzyklen_and_pruefmittel_with_ampel(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde, bezeichnung="Verteilung Keller")

    async with system_session() as session:
        session.add(
            Pruefzyklus(
                mandant_id=mandant.id,
                anlage_id=anlage.id,
                bezeichnung="E-Check",
                intervall_monate=12,
                naechste_pruefung_am=date.today() - timedelta(days=2),  # ueberfaellig
            )
        )
        session.add(
            Pruefmittel(
                mandant_id=mandant.id,
                bezeichnung="Multimeter",
                kalibrierintervall_monate=12,
                naechste_kalibrierung_am=date.today() + timedelta(days=3),  # bald faellig
            )
        )

    token = await login(client, admin.email, "pw-123456")
    resp = await client.get("/api/stories", headers=auth_headers(token))
    fristen = resp.json()["fristen"]
    assert len(fristen) == 2

    pruefzyklus_item = next(f for f in fristen if f["ziel_typ"] == "anlage")
    assert pruefzyklus_item["ampel"] == "rot"  # ueberfaellig

    pruefmittel_item = next(f for f in fristen if f["ziel_typ"] == "pruefmittel")
    assert pruefmittel_item["ampel"] == "gelb"  # innerhalb der Gelb-Schwelle


@pytest.mark.asyncio
async def test_fristen_excludes_pruefzyklus_beyond_horizon(
    client, make_mandant, make_user, make_kunde, make_anlage
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    anlage = await make_anlage(mandant=mandant, kunde=kunde)

    async with system_session() as session:
        session.add(
            Pruefzyklus(
                mandant_id=mandant.id,
                anlage_id=anlage.id,
                bezeichnung="Fern faellig",
                intervall_monate=12,
                naechste_pruefung_am=date.today() + timedelta(days=365),
            )
        )

    token = await login(client, admin.email, "pw-123456")
    resp = await client.get("/api/stories", headers=auth_headers(token))
    assert resp.json()["fristen"] == []
