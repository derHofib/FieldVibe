"""Zustand der Hintergrundjobs (Tabelle job_laeufe): Lese- und Schreibzugriff.

Immer ueber system_session -- die Tabelle hat zwar RLS, enthaelt aber auch
systemweite Zeilen (mandant_id NULL) und wird nur vom Worker/der Health-Pruefung
benutzt.
"""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import system_session
from app.models.job_lauf import JobLauf

# Fehlertext in der DB begrenzen -- Exception-Texte koennen sehr lang werden.
_MAX_FEHLER_ZEICHEN = 500


def _jetzt(jetzt: datetime | None) -> datetime:
    return jetzt or datetime.now(timezone.utc)


async def markiere_lauf(
    session: AsyncSession,
    job: str,
    mandant_id: UUID | None = None,
    *,
    erfolg: bool,
    ergebnis: dict | None = None,
    fehler: str | None = None,
    jetzt: datetime | None = None,
) -> None:
    """Haelt das Ergebnis eines Laufs fest. Nur ein Erfolg setzt letzter_lauf_am
    (und damit "erledigt"); ein Fehler zaehlt hoch und setzt nur den Versuch."""
    jetzt = _jetzt(jetzt)
    werte = {"job": job, "mandant_id": mandant_id, "letzter_versuch_am": jetzt}
    update = {"letzter_versuch_am": jetzt}
    if erfolg:
        werte |= {"letzter_lauf_am": jetzt, "letzter_fehler": None, "fehler_in_folge": 0, "ergebnis": ergebnis}
        update |= {"letzter_lauf_am": jetzt, "letzter_fehler": None, "fehler_in_folge": 0, "ergebnis": ergebnis}
    else:
        text = (fehler or "unbekannter Fehler")[:_MAX_FEHLER_ZEICHEN]
        werte |= {"letzter_fehler": text, "fehler_in_folge": 1}
        update |= {"letzter_fehler": text, "fehler_in_folge": JobLauf.fehler_in_folge + 1}

    stmt = pg_insert(JobLauf).values(**werte)
    if mandant_id is None:
        stmt = stmt.on_conflict_do_update(
            index_elements=[JobLauf.job], index_where=JobLauf.mandant_id.is_(None), set_=update
        )
    else:
        stmt = stmt.on_conflict_do_update(
            index_elements=[JobLauf.job, JobLauf.mandant_id],
            index_where=JobLauf.mandant_id.is_not(None),
            set_=update,
        )
    await session.execute(stmt)


async def heartbeat(job: str, *, jetzt: datetime | None = None) -> None:
    """Systemweiter Lebenszeichen-Eintrag (eigene kurze Transaktion)."""
    async with system_session() as session:
        await markiere_lauf(session, job, None, erfolg=True, jetzt=jetzt)


async def lade_laeufe(session: AsyncSession, job: str) -> dict[UUID | None, JobLauf]:
    zeilen = (await session.execute(select(JobLauf).where(JobLauf.job == job))).scalars().all()
    return {z.mandant_id: z for z in zeilen}
