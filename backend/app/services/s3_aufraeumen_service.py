"""Objektspeicher aufraeumen, nachdem ein Datensatz endgueltig geloescht wurde.

Ablauf: purge() legt in derselben Transaktion wie das DELETE je betroffenem Objektbereich
einen Auftrag an (s3_loeschauftraege). Erst NACH dem COMMIT (after_commit-Hook, als
Hintergrund-Task) und zusaetzlich im Worker werden die Objekte entfernt -- bei einem
Rollback verschwindet nichts, bei einem Absturz nach dem Commit bleibt der Auftrag
offen. Fehler (Object-Lock-Retention, S3 nicht erreichbar) werden protokolliert und mit
Wartezeit wiederholt; nach MAX_VERSUCHE steht der Auftrag auf "fehler" und bleibt in der
Retry-Liste (GET /api/aufbewahrung/s3-loeschauftraege) sichtbar."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.session import system_session
from app.models.s3_loeschauftrag import S3Loeschauftrag
from app.services import storage_service

logger = logging.getLogger("app.s3_aufraeumen")

MAX_VERSUCHE = 10
_NACH_COMMIT_KEY = "s3_aufraeumen_nach_commit"
_tasks: set[asyncio.Task] = set()

# Entitaetstyp -> Pfadsegment unter dem Mandantenpraefix bzw. (Altobjekte) an der Wurzel.
_PFAD_JE_ENTITAET = {
    "vorgang": "vorgaenge",
    "rechnung": "rechnungen",
    "eingangsrechnung": "eingangsrechnungen",
    "kunde": "kunden",
}


def prefixe_fuer(entity_typ: str, entity_id: UUID, mandant_id: UUID) -> list[str]:
    """Neues Schema (mandanten/<id>/<bereich>/<id>/) und Altschema (<bereich>/<id>/):
    Altobjekte werden nicht umgezogen, muessen beim Loeschen aber mit weg."""
    bereich = _PFAD_JE_ENTITAET.get(entity_typ)
    if bereich is None:
        return []
    return [f"{storage_service.mandant_prefix(mandant_id)}{bereich}/{entity_id}/", f"{bereich}/{entity_id}/"]


async def vormerken(
    session: AsyncSession, *, mandant_id: UUID, entity_typ: str, entity_id: UUID
) -> list[S3Loeschauftrag]:
    auftraege = [
        S3Loeschauftrag(mandant_id=mandant_id, prefix=prefix, anlass=f"{entity_typ}:{entity_id}")
        for prefix in prefixe_fuer(entity_typ, entity_id, mandant_id)
    ]
    for a in auftraege:
        session.add(a)
    if auftraege:
        session.sync_session.info[_NACH_COMMIT_KEY] = True
    return auftraege


async def verarbeite(limit: int = 50) -> dict[str, int]:
    """Arbeitet faellige Auftraege ab. Idempotent und parallel sicher (SKIP LOCKED)."""
    erledigt = fehlgeschlagen = 0
    jetzt = datetime.now(timezone.utc)
    async with system_session() as session:
        auftraege = (
            await session.execute(
                select(S3Loeschauftrag)
                .where(S3Loeschauftrag.status == "offen", S3Loeschauftrag.naechster_versuch_am <= jetzt)
                .order_by(S3Loeschauftrag.erstellt_am)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        for auftrag in auftraege:
            try:
                await storage_service.delete_prefix(auftrag.prefix)
            except Exception as exc:  # noqa: BLE001 -- jeder S3-Fehler heisst: spaeter erneut
                auftrag.versuche += 1
                auftrag.letzter_fehler = str(exc)[:500]
                auftrag.naechster_versuch_am = jetzt + timedelta(minutes=min(2**auftrag.versuche, 24 * 60))
                if auftrag.versuche >= MAX_VERSUCHE:
                    auftrag.status = "fehler"
                fehlgeschlagen += 1
                logger.warning("S3-Aufraeumen fehlgeschlagen (%s, Versuch %d): %s", auftrag.prefix, auftrag.versuche, exc)
            else:
                auftrag.status = "erledigt"
                auftrag.erledigt_am = jetzt
                auftrag.letzter_fehler = None
                erledigt += 1
    return {"erledigt": erledigt, "fehlgeschlagen": fehlgeschlagen}


async def _hintergrund() -> None:
    try:
        await verarbeite()
    except Exception:
        logger.exception("S3-Aufraeumen im Hintergrund fehlgeschlagen; der Worker holt es nach")


def hintergrund_tasks() -> list[asyncio.Task]:
    return list(_tasks)


@event.listens_for(Session, "after_commit")
def _nach_commit(session: Session) -> Any:
    if not session.info.pop(_NACH_COMMIT_KEY, False):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # ohne laufende Schleife (Skript): der Worker raeumt auf
    task = loop.create_task(_hintergrund())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


@event.listens_for(Session, "after_soft_rollback")
def _nach_rollback(session: Session, previous_transaction) -> None:
    if previous_transaction.parent is None:
        session.info.pop(_NACH_COMMIT_KEY, None)
