"""Gemeinsamer Rahmen fuer Worker-Jobs, die je Mandant in einer eigenen
Mandanten-Session (RLS) laufen statt in einer RLS-umgehenden system_session."""
import logging
from collections.abc import Awaitable, Callable, Iterable
from typing import TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import tenant_session
from app.services.worker_system import aktive_mandanten_ids

logger = logging.getLogger("app.worker")

T = TypeVar("T")


async def je_mandant_ergebnisse(
    mandant_ids: Iterable[UUID], arbeit: Callable[[UUID], Awaitable[T]]
) -> list[T]:
    """Fuehrt `arbeit` je Mandant aus. Ein Fehler stoppt die uebrigen Mandanten nicht;
    erst am Ende wird der erste Fehler erneut geworfen, damit der Aufrufer (job_runner)
    den Lauf wie bisher als fehlgeschlagen vermerkt."""
    ergebnisse: list[T] = []
    erster_fehler: Exception | None = None
    for mandant_id in mandant_ids:
        try:
            ergebnisse.append(await arbeit(mandant_id))
        except Exception as exc:
            logger.exception("Worker-Arbeit fuer Mandant %s fehlgeschlagen", mandant_id)
            if erster_fehler is None:
                erster_fehler = exc
    if erster_fehler is not None:
        raise erster_fehler
    return ergebnisse


async def je_mandant(
    mandant_ids: list[UUID] | None,
    arbeit: Callable[[AsyncSession, UUID], Awaitable[dict]],
) -> dict:
    """Wie je_mandant_ergebnisse, jeweils in tenant_session(mandant_id=m); die Zaehler-
    Dicts der Mandanten werden aufsummiert. None = alle aktiven Mandanten."""
    ids = mandant_ids if mandant_ids is not None else await aktive_mandanten_ids()

    async def _einer(mandant_id: UUID) -> dict:
        async with tenant_session(mandant_id=mandant_id, is_super_admin=False) as session:
            return await arbeit(session, mandant_id)

    summe: dict = {}
    for ergebnis in await je_mandant_ergebnisse(ids, _einer):
        for schluessel, wert in ergebnis.items():
            summe[schluessel] = summe.get(schluessel, 0) + wert
    return summe
