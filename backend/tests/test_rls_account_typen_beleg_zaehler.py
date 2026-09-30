"""RLS-Nachzug (Migration 0090): account_typen und beleg_zaehler waren bis
dahin nur per Code-Pruefung mandantengetrennt."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.session import system_session, tenant_session
from app.services.numbering_service import next_rechnungsnummer


@pytest.mark.asyncio
async def test_account_typen_sind_pro_mandant_getrennt(make_mandant, make_user):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    await make_user(mandant=mandant_a, role="techniker", password="pw-123456")
    await make_user(mandant=mandant_b, role="techniker", password="pw-123456")

    async with tenant_session(mandant_id=mandant_a.id, is_super_admin=False) as session:
        result = await session.execute(text("SELECT DISTINCT mandant_id FROM account_typen"))
        assert {str(r.mandant_id) for r in result.fetchall()} == {str(mandant_a.id)}

        with pytest.raises(DBAPIError):
            async with session.begin_nested():
                await session.execute(
                    text("INSERT INTO account_typen (id, mandant_id, name) VALUES (gen_random_uuid(), :m, 'Fremd')"),
                    {"m": str(mandant_b.id)},
                )

    async with system_session() as session:
        result = await session.execute(text("SELECT DISTINCT mandant_id FROM account_typen"))
        assert {str(r.mandant_id) for r in result.fetchall()} == {str(mandant_a.id), str(mandant_b.id)}


@pytest.mark.asyncio
async def test_rechnungsnummern_zaehler_pro_mandant_und_isoliert(make_mandant):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")

    async with tenant_session(mandant_id=mandant_a.id, is_super_admin=False) as session:
        assert await next_rechnungsnummer(session, mandant_a.id) == "R-00001"
        assert await next_rechnungsnummer(session, mandant_a.id) == "R-00002"
    async with tenant_session(mandant_id=mandant_b.id, is_super_admin=False) as session:
        assert await next_rechnungsnummer(session, mandant_b.id) == "R-00001"

    async with tenant_session(mandant_id=mandant_a.id, is_super_admin=False) as session:
        result = await session.execute(text("SELECT mandant_id, naechste_nummer FROM beleg_zaehler"))
        zeilen = result.fetchall()
        assert [(str(z.mandant_id), z.naechste_nummer) for z in zeilen] == [(str(mandant_a.id), 3)]

        # Fremden Zaehler hochzuzaehlen darf nicht gehen: weder per Upsert
        # (WITH CHECK) noch als blosses UPDATE (USING blendet die Zeile aus).
        with pytest.raises(DBAPIError):
            async with session.begin_nested():
                await next_rechnungsnummer(session, mandant_b.id)
        res = await session.execute(
            text("UPDATE beleg_zaehler SET naechste_nummer = 99 WHERE mandant_id = :m"),
            {"m": str(mandant_b.id)},
        )
        assert res.rowcount == 0
