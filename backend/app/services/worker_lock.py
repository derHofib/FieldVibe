from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text

from app.db.session import engine

# Feste, fuer diese Anwendung eindeutige Konstanten -- pg_advisory_lock nimmt
# einen beliebigen bigint als Schluessel; es gibt hier keine andere
# Verwendung dieses Wertebereichs, die kollidieren koennte. Eigener
# Schluessel fuer den Mail-Sync-Takt (siehe app/worker.py), damit der
# haeufigere Mail-Sync-Tick nicht auf den stuendlichen Scheduler-Tick warten
# muss (und umgekehrt) -- beide sollen unabhaengig voneinander laufen
# duerfen, nur jeweils sich selbst gegen doppelte Worker-Container schuetzen.
_WORKER_LOCK_KEY = 9_182_736_451
_MAIL_SYNC_LOCK_KEY = 9_182_736_452


@asynccontextmanager
async def worker_lock(key: int = _WORKER_LOCK_KEY) -> AsyncIterator[bool]:
    """Session-Level Postgres-Advisory-Lock, um zu verhindern, dass zwei
    gleichzeitig laufende Worker-Container (z.B. bei einem versehentlichen
    Scale-Up ueber die dokumentierte 'ein Worker pro Deployment'-Annahme aus
    Phase 5 hinaus) denselben Scheduler-/Mahnwesen-Lauf doppelt ausfuehren.

    Haelt fuer die Dauer des `async with`-Blocks eine dedizierte Connection
    offen -- pg_advisory_lock ist an die Connection gebunden, nicht an die
    Transaktion, daher reicht ein normaler pooled Session-Checkout dafuer
    nicht: die Connection muss waehrend der gesamten kritischen Sektion
    exklusiv gehalten werden. Gibt via `yield` zurueck, ob der Lock erlangt
    wurde (`pg_try_advisory_lock` blockiert nicht) -- der Aufrufer muss den
    kritischen Abschnitt bei `False` selbst ueberspringen.
    """
    async with engine.connect() as conn:
        acquired = bool(
            (await conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})).scalar()
        )
        try:
            yield acquired
        finally:
            if acquired:
                await conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})


def mail_sync_lock() -> AsyncIterator[bool]:
    return worker_lock(_MAIL_SYNC_LOCK_KEY)
