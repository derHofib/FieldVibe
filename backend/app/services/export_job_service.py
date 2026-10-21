"""Asynchrone Mandanten-Exporte (Vollexport, Z3): Auftrag -> Verarbeitung -> Download -> Ablauf.

Der Request legt nur den Auftrag an (Status "wartend") und antwortet sofort. Verarbeitet wird
nach dem COMMIT in einem Hintergrund-Task der API und, falls dieser nicht lief, vom Worker
(FOR UPDATE SKIP LOCKED: jeder Auftrag genau einmal). Das Ergebnis-ZIP liegt im
Objektspeicher, 7 Tage abrufbar (signierte, kurz gueltige URL), danach entfernt der Worker
es; die Zeile bleibt als Nachweis."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import tempfile
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.session import system_session, tenant_session
from app.models.mandant_export import MandantExport
from app.services import audit_service, storage_service, vollexport_service
from app.services.export_zip import ZipSchreiber

logger = logging.getLogger("app.export")

AUFBEWAHRUNG_TAGE = 7
DOWNLOAD_GUELTIG_SEKUNDEN = 15 * 60
# Ein "laeuft"-Auftrag ohne Ergebnis nach dieser Zeit gilt als abgebrochen (Absturz/Neustart).
MAX_LAUFZEIT = timedelta(hours=2)
_NACH_COMMIT_KEY = "export_nach_commit"
_tasks: set[asyncio.Task] = set()


class ExportLaeuftBereits(Exception):
    pass


async def anfordern(
    session: AsyncSession, *, mandant_id: UUID, user_id: UUID, art: str, parameter: dict | None = None
) -> MandantExport:
    """Legt einen Auftrag an. Hoechstens ein wartender/laufender Export je Mandant
    (Teil-Unique-Index in der DB als letzte Instanz gegen gleichzeitige Anfragen)."""
    aktiv = await session.scalar(
        select(MandantExport.id).where(
            MandantExport.mandant_id == mandant_id, MandantExport.status.in_(("wartend", "laeuft"))
        )
    )
    if aktiv is not None:
        raise ExportLaeuftBereits()
    job = MandantExport(
        mandant_id=mandant_id, art=art, angefordert_von=user_id, parameter=jsonable_encoder(parameter or {})
    )
    session.add(job)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ExportLaeuftBereits() from exc
    await audit_service.export_protokollieren(
        session, mandant_id=mandant_id, actor_user_id=user_id, art=f"{art}_angefordert", export_id=str(job.id), **(parameter or {})
    )
    session.sync_session.info[_NACH_COMMIT_KEY] = True
    return job


async def verarbeite_naechsten() -> UUID | None:
    """Nimmt den aeltesten wartenden Auftrag und fuehrt ihn aus. None, wenn keiner wartet."""
    jetzt = datetime.now(timezone.utc)
    async with system_session() as session:
        haengende = (
            await session.execute(
                select(MandantExport).where(
                    MandantExport.status == "laeuft", MandantExport.gestartet_am < jetzt - MAX_LAUFZEIT
                )
            )
        ).scalars().all()
        for h in haengende:
            h.status = "fehler"
            h.fehler = "Abgebrochen (Zeitüberschreitung oder Neustart)"
        job = (
            await session.execute(
                select(MandantExport)
                .where(MandantExport.status == "wartend")
                .order_by(MandantExport.angefordert_am)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if job is None:
            return None
        job.status = "laeuft"
        job.gestartet_am = jetzt
        job_id, mandant_id, art, parameter, user_id = job.id, job.mandant_id, job.art, dict(job.parameter), job.angefordert_von

    try:
        ergebnis = await _erzeugen(job_id, mandant_id, art, parameter)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Export %s fehlgeschlagen", job_id)
        async with system_session() as session:
            j = await session.get(MandantExport, job_id)
            j.status = "fehler"
            j.fehler = f"{type(exc).__name__}: {exc}"[:500]
            await audit_service.log_action(
                session,
                aktion=f"export_{art}_fehlgeschlagen",
                mandant_id=mandant_id,
                entity_type="export",
                entity_id=job_id,
                payload={"fehler": type(exc).__name__},
                akteur_typ="system",
            )
        return job_id

    async with system_session() as session:
        j = await session.get(MandantExport, job_id)
        j.status = "fertig"
        j.fertig_am = datetime.now(timezone.utc)
        j.laeuft_ab_am = j.fertig_am + timedelta(days=AUFBEWAHRUNG_TAGE)
        j.object_key = ergebnis["key"]
        j.groesse_bytes = ergebnis["groesse"]
        j.sha256 = ergebnis["sha256"]
        j.anzahl_dateien = ergebnis["anzahl_dateien"]
        await audit_service.log_action(
            session,
            aktion=f"export_{art}_fertig",
            mandant_id=mandant_id,
            actor_user_id=user_id,
            entity_type="export",
            entity_id=job_id,
            payload={"sha256": ergebnis["sha256"], "groesse_bytes": ergebnis["groesse"], "dateien": ergebnis["anzahl_dateien"]},
        )
    return job_id


async def _erzeugen(job_id: UUID, mandant_id: UUID, art: str, parameter: dict) -> dict:
    # Eine eigene Mandanten-Session (RLS) liest die Daten; das ZIP entsteht auf der Platte.
    with tempfile.TemporaryFile() as tmp:
        zip_ = ZipSchreiber(tmp)
        try:
            async with tenant_session(mandant_id=mandant_id, is_super_admin=False) as session:
                if art == "vollexport":
                    kopf = await vollexport_service.erzeuge(session, zip_, mandant_id)
                elif art == "z3":
                    from app.services import z3_service

                    kopf = await z3_service.erzeuge(
                        session, zip_, mandant_id, date.fromisoformat(parameter["von"]), date.fromisoformat(parameter["bis"])
                    )
                else:
                    raise ValueError(f"Unbekannte Export-Art: {art}")
        except BaseException:
            zip_.abbrechen()
            raise
        zip_.manifest_schreiben(kopf)
        anzahl = len(zip_.dateien) + 1
        zip_.schliessen()

        groesse = tmp.tell()
        tmp.seek(0)
        digest = hashlib.sha256()
        while chunk := tmp.read(1024 * 1024):
            digest.update(chunk)
        tmp.seek(0)
        key = f"{storage_service.mandant_prefix(mandant_id)}exporte/{job_id}/{art}-{datetime.now(timezone.utc):%Y%m%d}.zip"
        await storage_service.upload_file(key, tmp, "application/zip")
    return {"key": key, "groesse": groesse, "sha256": digest.hexdigest(), "anzahl_dateien": anzahl}


async def raeume_auf() -> int:
    """Entfernt abgelaufene Ergebnis-ZIPs (7 Tage); die Zeile bleibt als Nachweis."""
    jetzt = datetime.now(timezone.utc)
    entfernt = 0
    async with system_session() as session:
        faellig = (
            await session.execute(
                select(MandantExport).where(MandantExport.status == "fertig", MandantExport.laeuft_ab_am < jetzt)
            )
        ).scalars().all()
        for job in faellig:
            try:
                if job.object_key:
                    await storage_service.delete_object(job.object_key)
            except Exception:  # noqa: BLE001
                logger.warning("Export-ZIP %s konnte nicht entfernt werden, naechster Versuch folgt", job.id, exc_info=True)
                continue
            job.status = "abgelaufen"
            job.object_key = None
            entfernt += 1
            await audit_service.log_action(
                session,
                aktion=f"export_{job.art}_abgelaufen",
                mandant_id=job.mandant_id,
                entity_type="export",
                entity_id=job.id,
                akteur_typ="system",
            )
    return entfernt


def download_url(job: MandantExport) -> tuple[str, datetime]:
    gueltig_bis = datetime.now(timezone.utc) + timedelta(seconds=DOWNLOAD_GUELTIG_SEKUNDEN)
    url = storage_service.presigned_get_url(
        job.object_key,
        DOWNLOAD_GUELTIG_SEKUNDEN,
        dateiname=f"fieldvibe-{job.art}-{job.fertig_am:%Y%m%d}.zip",
    )
    return url, gueltig_bis


async def _hintergrund() -> None:
    try:
        while await verarbeite_naechsten() is not None:
            pass
    except Exception:
        logger.exception("Export im Hintergrund fehlgeschlagen; der Worker holt es nach")


def hintergrund_tasks() -> list[asyncio.Task]:
    return list(_tasks)


@event.listens_for(Session, "after_commit")
def _nach_commit(session: Session) -> None:
    if not session.info.pop(_NACH_COMMIT_KEY, False):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(_hintergrund())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


@event.listens_for(Session, "after_soft_rollback")
def _nach_rollback(session: Session, previous_transaction) -> None:
    if previous_transaction.parent is None:
        session.info.pop(_NACH_COMMIT_KEY, None)
