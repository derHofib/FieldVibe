import logging
import sys
import time
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
logger = logging.getLogger(__name__)

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


_audit_zuletzt: dict[str, float] = {}


def _aufrufer() -> str:
    # Huellen (diese Datei, contextlib) ueberspringen, statt eine feste Tiefe
    # anzunehmen -- die haengt an der contextmanager-Implementierung.
    frame = sys._getframe(1)
    while frame.f_back is not None and frame.f_globals.get("__name__") in (__name__, "contextlib"):
        frame = frame.f_back
    modul = frame.f_globals.get("__name__", "?")
    return f"{modul}:{frame.f_code.co_name}"


def _gedrosselt(grund: str, drosselung_s: int | None) -> bool:
    if drosselung_s is None:
        return False
    jetzt = time.monotonic()
    letzt = _audit_zuletzt.get(grund)
    if letzt is not None and jetzt - letzt < drosselung_s:
        return True
    _audit_zuletzt[grund] = jetzt
    return False


async def _system_session_protokollieren(grund: str, aufrufer: str) -> None:
    from app.services.audit_service import log_action

    async with async_session_maker() as session:
        async with session.begin():
            await _apply_tenant_context(session, mandant_id=None, is_super_admin=True)
            await log_action(
                session,
                aktion="system_session",
                akteur_typ="system",
                mandant_id=None,
                payload={"grund": grund, "aufrufer": aufrufer},
            )


@asynccontextmanager
async def system_session(
    *, grund: str, drosselung_s: int | None = None
) -> AsyncIterator[AsyncSession]:
    """Bypasses tenant RLS entirely (app.is_super_admin = true).

    Reserved for: the pre-authentication user lookup during login (the
    email is unique platform-wide, so which tenant it belongs to is not yet
    known), platform-level super_admin operations that span tenants, and
    seeding/administrative scripts.

    `grund` ist Pflicht: jedes Oeffnen schreibt einen audit_log-Eintrag
    (aktion "system_session", Grund + aufrufendes Modul:Funktion) in einer
    eigenen, vorab committeten Transaktion -- er bleibt also auch dann, wenn
    die Transaktion des Aufrufers zurueckgerollt wird. `drosselung_s` begrenzt
    das je Grund und Prozess auf einen Eintrag pro Zeitfenster (Worker-
    Polling wuerde den audit_log sonst jede Minute fluten).

    Scheitert der Audit-Eintrag, wird nur geloggt und die Session trotzdem
    geoeffnet: fail-closed wuerde bei einem Audit-Problem Login und Worker
    lahmlegen, was als Ausfall schwerer wiegt als die fehlende Zeile.
    Jeder Aufrufer, der im Namen eines Menschen handelt (nicht der reine
    Login-Lookup), schreibt weiterhin seinen eigenen Eintrag -- siehe
    app.services.audit_service.
    """
    if not grund or not grund.strip():
        raise ValueError("system_session braucht einen nicht leeren grund")
    if get_settings().system_session_audit and not _gedrosselt(grund, drosselung_s):
        try:
            await _system_session_protokollieren(grund, _aufrufer())
        except Exception:
            logger.exception("system_session-Audit fehlgeschlagen (grund=%s)", grund)
    async with async_session_maker() as session:
        async with session.begin():
            await _apply_tenant_context(session, mandant_id=None, is_super_admin=True)
            yield session
