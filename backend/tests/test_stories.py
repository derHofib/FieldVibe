from datetime import datetime, timedelta, timezone

import pytest

from app.db.session import system_session
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
