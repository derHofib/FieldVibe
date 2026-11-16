"""Phase 3: der RLS-Bypass haengt an der DB-Rolle (fieldvibe_system), nicht mehr an
einer Session-Variable. Eine App-Verbindung, die app.is_super_admin selbst setzt
(etwa nach einer SQL-Injection), gewinnt dadurch nichts."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.session import system_session, tenant_session


@pytest.fixture
async def zwei_mandanten(make_mandant, make_kunde):
    a = await make_mandant(name="Mandant A")
    b = await make_mandant(name="Mandant B")
    kunde_a = await make_kunde(mandant=a, name="Kunde A")
    kunde_b = await make_kunde(mandant=b, name="Kunde B")
    return a, b, kunde_a, kunde_b


@pytest.mark.asyncio
async def test_gesetzte_session_variable_oeffnet_fremde_mandanten_nicht(zwei_mandanten):
    a, b, kunde_a, kunde_b = zwei_mandanten
    async with tenant_session(mandant_id=a.id) as session:
        await session.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
        zeilen = (await session.execute(text("SELECT id, mandant_id FROM kunden"))).all()
        mandanten = (await session.execute(text("SELECT id FROM mandanten"))).all()
    assert {z.id for z in zeilen} == {kunde_a.id}
    assert not any(z.mandant_id == b.id for z in zeilen)
    assert {m.id for m in mandanten} == {a.id}


@pytest.mark.asyncio
async def test_gesetzte_session_variable_erlaubt_keine_fremden_schreibzugriffe(zwei_mandanten):
    a, b, _, kunde_b = zwei_mandanten
    async with tenant_session(mandant_id=a.id) as session:
        await session.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
        upd = await session.execute(
            text("UPDATE kunden SET name = 'gehackt' WHERE id = :id"), {"id": kunde_b.id}
        )
        dele = await session.execute(text("DELETE FROM kunden WHERE id = :id"), {"id": kunde_b.id})
        assert upd.rowcount == 0 and dele.rowcount == 0

    with pytest.raises(DBAPIError, match="row-level security"):
        async with tenant_session(mandant_id=a.id) as session:
            await session.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
            await session.execute(
                text(
                    "INSERT INTO kunden (id, mandant_id, kundennummer, name, portal_slug) "
                    "VALUES (gen_random_uuid(), :m, 'K-X', 'Eindringling', 'slug-x')"
                ),
                {"m": b.id},
            )

    async with system_session(grund="test") as session:
        name = (
            await session.execute(text("SELECT name FROM kunden WHERE id = :id"), {"id": kunde_b.id})
        ).scalar_one()
    assert name == "Kunde B"


@pytest.mark.asyncio
async def test_app_rolle_kann_plattform_integrationen_nicht_lesen(make_mandant):
    mandant = await make_mandant()
    async with system_session(grund="test") as session:
        await session.execute(
            text("INSERT INTO plattform_integrationen (typ, config, aktiv) VALUES ('smtp', '{}'::jsonb, true)")
        )
    async with tenant_session(mandant_id=mandant.id) as session:
        await session.execute(text("SELECT set_config('app.is_super_admin', 'true', true)"))
        assert (await session.execute(text("SELECT count(*) FROM plattform_integrationen"))).scalar_one() == 0
    async with system_session(grund="test") as session:
        assert (await session.execute(text("SELECT count(*) FROM plattform_integrationen"))).scalar_one() == 1


@pytest.mark.asyncio
async def test_system_session_sieht_beide_mandanten(zwei_mandanten):
    a, b, kunde_a, kunde_b = zwei_mandanten
    async with system_session(grund="test") as session:
        ids = {r.id for r in (await session.execute(text("SELECT id FROM kunden"))).all()}
        mandanten = {r.id for r in (await session.execute(text("SELECT id FROM mandanten"))).all()}
    assert {kunde_a.id, kunde_b.id} <= ids
    assert {a.id, b.id} <= mandanten
