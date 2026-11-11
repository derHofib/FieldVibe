import pytest
from sqlalchemy import select

from app.db.session import system_session
from app.models.vorgang import Vorgang
from app.seed import DEFAULT_PASSWORD, seed
from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_seed_weist_technikern_kunden_zu_und_ist_idempotent(client):
    await seed()
    await seed()

    token = await login(client, "technik1@mueller.example.de", DEFAULT_PASSWORD)
    feed = await client.get("/api/feed", headers=auth_headers(token))
    assert feed.status_code == 200
    assert len(feed.json()["items"]) > 0


@pytest.mark.asyncio
async def test_seed_abschluss_liegt_nach_anlage():
    await seed()

    async with system_session() as session:
        vorgaenge = (
            await session.execute(select(Vorgang).where(Vorgang.abgeschlossen_am.isnot(None)))
        ).scalars().all()
    assert vorgaenge
    assert all(v.abgeschlossen_am.replace(tzinfo=None) >= v.created_at.replace(tzinfo=None) for v in vorgaenge)
