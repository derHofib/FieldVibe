from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_settings = get_settings()

engine = create_async_engine(_settings.database_url, pool_pre_ping=True)

async_session_maker = async_sessionmaker(
    engine, expire_on_commit=False, autoflush=False
)


async def _apply_tenant_context(
    session: AsyncSession, *, mandant_id: UUID | None, is_super_admin: bool
) -> None:
    """Sets the Postgres session variables the RLS policies key off of.

    Uses set_config(..., true) inside the open transaction, which is the
    parametrized equivalent of `SET LOCAL` -- it is automatically reset at
    transaction end and never touches connection-pool state.
    """
    await session.execute(
        text("SELECT set_config('app.current_mandant', :val, true)"),
        {"val": str(mandant_id) if mandant_id else ""},
    )
    await session.execute(
        text("SELECT set_config('app.is_super_admin', :val, true)"),
        {"val": "true" if is_super_admin else "false"},
    )


@asynccontextmanager
async def tenant_session(
    *, mandant_id: UUID | None, is_super_admin: bool
) -> AsyncIterator[AsyncSession]:
    """Session scoped to a single tenant for the lifetime of one transaction.

    Every request from an authenticated, tenant-bound user (mandant_admin,
    disponent, techniker) goes through this. Row Level Security enforces the
    isolation at the database layer regardless of what the application code
    does or doesn't filter by.
    """
    async with async_session_maker() as session:
        async with session.begin():
            await _apply_tenant_context(
                session, mandant_id=mandant_id, is_super_admin=is_super_admin
            )
            yield session


@asynccontextmanager
async def system_session() -> AsyncIterator[AsyncSession]:
    """Bypasses tenant RLS entirely (app.is_super_admin = true).

    Reserved for: the pre-authentication user lookup during login (the
    email is unique platform-wide, so which tenant it belongs to is not yet
    known), platform-level super_admin operations that span tenants, and
    seeding/administrative scripts. Every caller of this function that acts
    on behalf of a human (as opposed to the login lookup itself) is expected
    to write an audit_log entry -- see app.services.audit_service.
    """
    async with async_session_maker() as session:
        async with session.begin():
            await _apply_tenant_context(session, mandant_id=None, is_super_admin=True)
            yield session
