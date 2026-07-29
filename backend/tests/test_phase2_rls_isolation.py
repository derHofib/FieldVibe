"""RLS isolation proof for the Phase 2 fachliche Kern tables, following the
same pattern established in test_rls_isolation.py for Phase 1."""

import pytest
from sqlalchemy import text

from app.db.session import tenant_session
from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_vorgang_list_is_scoped_to_own_mandant_via_api(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    admin_a = await make_user(mandant=mandant_a, role="mandant_admin", password="pw-123456")
    kunde_a = await make_kunde(mandant=mandant_a)
    kunde_b = await make_kunde(mandant=mandant_b)
    await make_vorgang(mandant=mandant_a, kunde=kunde_a, titel="Vorgang A")
    await make_vorgang(mandant=mandant_b, kunde=kunde_b, titel="Vorgang B")

    token = await login(client, admin_a.email, "pw-123456")
    resp = await client.get("/api/vorgaenge", headers=auth_headers(token))

    assert resp.status_code == 200
    titel = {v["titel"] for v in resp.json()}
    assert titel == {"Vorgang A"}


@pytest.mark.asyncio
async def test_manipulated_vorgang_id_across_tenants_returns_404(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    admin_a = await make_user(mandant=mandant_a, role="mandant_admin", password="pw-123456")
    kunde_b = await make_kunde(mandant=mandant_b)
    vorgang_b = await make_vorgang(mandant=mandant_b, kunde=kunde_b)

    token = await login(client, admin_a.email, "pw-123456")
    resp = await client.get(f"/api/vorgaenge/{vorgang_b.id}", headers=auth_headers(token))
    assert resp.status_code == 404

    events_resp = await client.get(
        f"/api/vorgaenge/{vorgang_b.id}/events", headers=auth_headers(token)
    )
    assert events_resp.status_code == 404


@pytest.mark.asyncio
async def test_raw_sql_cannot_read_other_mandants_vorgang_events(
    make_mandant, make_kunde, make_vorgang
):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    kunde_a = await make_kunde(mandant=mandant_a)
    kunde_b = await make_kunde(mandant=mandant_b)
    vorgang_a = await make_vorgang(mandant=mandant_a, kunde=kunde_a)
    vorgang_b = await make_vorgang(mandant=mandant_b, kunde=kunde_b)

    from app.db.session import system_session
    from app.models.vorgang_event import VorgangEvent

    async with system_session() as session:
        session.add(
            VorgangEvent(
                mandant_id=mandant_b.id,
                vorgang_id=vorgang_b.id,
                event_type="kommentar",
                body="Geheime Mandant-B-Notiz",
            )
        )
        await session.flush()

    async with tenant_session(mandant_id=mandant_a.id, is_super_admin=False) as session:
        result = await session.execute(
            text("SELECT * FROM vorgang_events WHERE vorgang_id = :vid"),
            {"vid": str(vorgang_b.id)},
        )
        assert result.fetchall() == []

        result_all = await session.execute(text("SELECT mandant_id FROM vorgang_events"))
        seen = {str(row.mandant_id) for row in result_all.fetchall()}
        assert seen <= {str(mandant_a.id)}

        # And the FK-existence caveat from anlagen._require_own_kunde: even
        # though a raw INSERT referencing mandant_b's Kunde would pass the
        # FK constraint (constraint checks run with owner privileges and
        # ignore RLS), a normal SELECT on that Kunde from mandant_a's
        # session must still come back empty.
        kunde_check = await session.execute(
            text("SELECT * FROM kunden WHERE id = :kid"), {"kid": str(kunde_b.id)}
        )
        assert kunde_check.fetchall() == []


@pytest.mark.asyncio
async def test_tags_are_isolated_per_mandant(client, make_mandant, make_user):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    admin_a = await make_user(mandant=mandant_a, role="mandant_admin", password="pw-123456")
    admin_b = await make_user(mandant=mandant_b, role="mandant_admin", password="pw-123456")
    token_a = await login(client, admin_a.email, "pw-123456")
    token_b = await login(client, admin_b.email, "pw-123456")

    # Gleiches Label ist in unterschiedlichen Mandanten unabhängig erlaubt.
    resp_a = await client.post(
        "/api/tags", headers=auth_headers(token_a), json={"label": "dringend"}
    )
    resp_b = await client.post(
        "/api/tags", headers=auth_headers(token_b), json={"label": "dringend"}
    )
    assert resp_a.status_code == 201
    assert resp_b.status_code == 201
    assert resp_a.json()["id"] != resp_b.json()["id"]

    list_a = await client.get("/api/tags", headers=auth_headers(token_a))
    assert len(list_a.json()) == 1
