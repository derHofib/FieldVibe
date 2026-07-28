"""Proves multi-tenant isolation is enforced by Postgres Row Level Security
itself, not merely by application-level filtering -- per the requirement in
section 3 of the spec ("Integrationstest, der beweist, dass ein User von
Mandant A auch bei manipulierter Query keine Daten von Mandant B lesen
kann")."""

import pytest
from sqlalchemy import text

from app.db.session import tenant_session
from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_user_list_is_scoped_to_own_mandant_via_api(
    client, make_mandant, make_user
):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    admin_a = await make_user(mandant=mandant_a, role="mandant_admin", password="pw-123456")
    await make_user(mandant=mandant_a, role="techniker", password="pw-123456")
    await make_user(mandant=mandant_b, role="techniker", password="pw-123456")

    token = await login(client, admin_a.email, "pw-123456")
    resp = await client.get("/api/users", headers=auth_headers(token))

    assert resp.status_code == 200
    returned_mandant_ids = {u["mandant_id"] for u in resp.json()}
    assert returned_mandant_ids == {str(mandant_a.id)}


@pytest.mark.asyncio
async def test_manipulated_path_param_cannot_reach_other_mandants_user(
    client, make_mandant, make_user
):
    """Mandant A's admin tries to PATCH a user id that actually belongs to
    Mandant B by directly guessing/supplying the UUID in the URL -- the
    classic "manipulated query" attack against an object-level endpoint.
    RLS makes the row invisible before the ownership check even runs, so the
    server can only ever answer 404, never leak whether the id exists."""
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    admin_a = await make_user(mandant=mandant_a, role="mandant_admin", password="pw-123456")
    victim_in_b = await make_user(
        mandant=mandant_b, role="techniker", password="pw-123456"
    )

    token = await login(client, admin_a.email, "pw-123456")
    resp = await client.patch(
        f"/api/users/{victim_in_b.id}",
        headers=auth_headers(token),
        json={"aktiv": False},
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_raw_sql_with_attacker_supplied_filter_still_returns_nothing(
    make_mandant, make_user
):
    """Even if application code had a bug and executed a raw, unfiltered-by-
    design query using an attacker-controlled mandant_id, the database
    itself refuses to return rows outside the session's tenant context.
    This is the direct proof that isolation is enforced at the DB layer via
    Row Level Security, independent of any application code correctness."""
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    await make_user(mandant=mandant_a, role="techniker", password="pw-123456")
    await make_user(mandant=mandant_b, role="techniker", password="pw-123456")
    await make_user(mandant=mandant_b, role="disponent", password="pw-123456")

    async with tenant_session(mandant_id=mandant_a.id, is_super_admin=False) as session:
        # Deliberately query for mandant B's data from within mandant A's
        # session context -- simulating a manipulated/forged filter.
        result = await session.execute(
            text("SELECT * FROM users WHERE mandant_id = :b"), {"b": str(mandant_b.id)}
        )
        assert result.fetchall() == []

        # An unfiltered SELECT * from within the same session must also only
        # ever surface mandant A's own rows.
        all_rows = await session.execute(text("SELECT mandant_id FROM users"))
        seen = {str(row.mandant_id) for row in all_rows.fetchall()}
        assert seen == {str(mandant_a.id)}


@pytest.mark.asyncio
async def test_raw_sql_cannot_read_other_mandants_row_directly(
    make_mandant, make_user
):
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    await make_user(mandant=mandant_a, role="techniker", password="pw-123456")

    async with tenant_session(mandant_id=mandant_a.id, is_super_admin=False) as session:
        result = await session.execute(
            text("SELECT * FROM mandanten WHERE id = :b"), {"b": str(mandant_b.id)}
        )
        assert result.fetchall() == []


@pytest.mark.asyncio
async def test_super_admin_session_intentionally_bypasses_rls(
    make_mandant, make_user
):
    """The counterpart proof: cross-tenant visibility exists, but only for
    the dedicated, explicitly-scoped super_admin session path."""
    mandant_a = await make_mandant(name="Mandant A")
    mandant_b = await make_mandant(name="Mandant B")
    await make_user(mandant=mandant_a, role="techniker", password="pw-123456")
    await make_user(mandant=mandant_b, role="techniker", password="pw-123456")

    from app.db.session import system_session

    async with system_session() as session:
        result = await session.execute(text("SELECT mandant_id FROM users"))
        seen = {str(row.mandant_id) for row in result.fetchall()}
        assert seen == {str(mandant_a.id), str(mandant_b.id)}
