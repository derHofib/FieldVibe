"""Zustandsgefuehrter Ablauf der Hintergrundjobs.

Frueher pruefte der Worker nur zur vollen Stunde `stunde == jetzt.hour`: wer zu
dieser Minute nicht lief (Neustart, Ausfall, Deploy), liess den Lauf dieses Tages
aus. Jetzt entscheidet job_laeufe: ein Job ist faellig, wenn sein letzter
erfolgreicher Lauf VOR dem juengsten Slot liegt (taeglich zur Mandanten-Stunde
bzw. stuendlich). Die Jobs selbst sind zustandsbasiert (offener_vorgang_id,
nachgefasst_am, mahnstufe ...), ein einzelner nachgeholter Lauf erledigt daher
alles Aufgelaufene -- Tage werden nie einzeln wiederholt.

Mehrfach-Worker: der gesamte Tick laeuft unter einem Postgres-Advisory-Lock
(worker_lock); die Jobs sperren ihre Kandidatenzeilen zusaetzlich mit
FOR UPDATE SKIP LOCKED.
"""
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging_config import job_kontext
from app.db.session import system_session
from app.models.job_lauf import JobLauf
from app.models.mandant import Mandant
from app.services.datenimport.lauf import raeume_auf as raeume_datenimport_auf
from app.services.email_ingest_service import run_email_ingest
from app.services.fehlerbericht_service import loesche_abgelaufene_fehlerberichte
from app.services.job_state_service import lade_laeufe, markiere_lauf
from app.services.kreditorenbuchhaltung_service import run_kreditoren_faelligkeits_check
from app.services.mahnwesen_service import run_mahnwesen_eskalation
from app.services.scheduler_service import (
    run_angebot_nachfassen,
    run_dauerauftraege_scheduler,
    run_prioritaet_scheduler,
    run_pruefzyklen_scheduler,
    run_wiedervorlage_scheduler,
)
from app.services.worker_lock import worker_lock

logger = logging.getLogger("app.worker")

MandantenJob = Callable[[list[UUID]], Awaitable[dict]]
SystemJob = Callable[[], Awaitable[object]]

# Reihenfolge wie im bisherigen stuendlichen Tick.
TAEGLICHE_JOBS: dict[str, MandantenJob] = {
    "pruefzyklen": run_pruefzyklen_scheduler,
    "dauerauftraege": run_dauerauftraege_scheduler,
    "prioritaet": run_prioritaet_scheduler,
    "wiedervorlage": run_wiedervorlage_scheduler,
    "angebot_nachfassen": run_angebot_nachfassen,
    "mahnwesen": run_mahnwesen_eskalation,
    "kreditoren": run_kreditoren_faelligkeits_check,
}


async def _email_ingest() -> dict:
    return await run_email_ingest()


async def _datenimport_aufraeumen() -> dict:
    return await raeume_datenimport_auf()


async def _fehlerbericht_aufbewahrung() -> dict:
    return {"geloescht": await loesche_abgelaufene_fehlerberichte()}


# (Name, Funktion, Taktung): "stuendlich" = ein Lauf je UTC-Stunde, "taeglich" = einer je
# UTC-Tag ab scheduler_default_stunde_utc (Aufbewahrung gilt plattformweit).
SYSTEM_JOBS: dict[str, tuple[SystemJob, str]] = {
    "email_ingest": (_email_ingest, "stuendlich"),
    # Stuendlich: die Quelldatei eines Imports soll nach 24 Stunden weg sein, nicht erst am naechsten Tag.
    "datenimport_aufraeumen": (_datenimport_aufraeumen, "stuendlich"),
    "fehlerbericht_aufbewahrung": (_fehlerbericht_aufbewahrung, "taeglich"),
}


def letzter_slot(jetzt: datetime, stunde_utc: int) -> datetime:
    """Juengster Zeitpunkt <= jetzt, der auf `stunde_utc`:00 UTC faellt."""
    slot = jetzt.astimezone(timezone.utc).replace(hour=stunde_utc, minute=0, second=0, microsecond=0)
    return slot - timedelta(days=1) if slot > jetzt else slot


def ist_faellig(lauf: JobLauf | None, slot: datetime, jetzt: datetime, retry_minuten: int) -> bool:
    if lauf is not None and lauf.letzter_lauf_am is not None and lauf.letzter_lauf_am >= slot:
        return False
    # Nach einem Fehlschlag nicht bei jedem Tick neu versuchen, sondern erst nach der Pause.
    if lauf is not None and lauf.letzter_versuch_am is not None and lauf.fehler_in_folge > 0:
        return jetzt - lauf.letzter_versuch_am >= timedelta(minutes=retry_minuten)
    return True


def _pruefe_verzug(job: str, lauf: JobLauf | None, slot: datetime, max_tage: int) -> None:
    if lauf is None or lauf.letzter_lauf_am is None:
        return
    verzug = slot - lauf.letzter_lauf_am
    if verzug > timedelta(days=max_tage):
        # Ausfall laenger als die Obergrenze: der Lauf wird trotzdem einmal nachgeholt (die Jobs sind
        # zustandsbasiert), aber das ist ein Betriebsproblem und gehoert in den Alarm.
        logger.error(
            "Job %s lief zuletzt vor %d Tagen (Grenze %d) -- wird einmal nachgeholt",
            job, verzug.days, max_tage, extra={"event": "job_nachholen_ueberschritten"},
        )
    elif verzug >= timedelta(hours=1):
        logger.warning("Job %s holt einen versaeumten Lauf nach (letzter Lauf %s)", job, lauf.letzter_lauf_am.isoformat(),
                       extra={"event": "job_nachholen"})


async def faellige_mandanten(session, job: str, jetzt: datetime) -> list[UUID]:
    s = get_settings()
    laeufe = await lade_laeufe(session, job)
    ergebnis: list[UUID] = []
    mandanten = (await session.execute(
        select(Mandant.id, Mandant.scheduler_stunde_utc).where(Mandant.status == "aktiv")
    )).all()
    for mandant_id, stunde in mandanten:
        slot = letzter_slot(jetzt, stunde if stunde is not None else s.scheduler_default_stunde_utc)
        lauf = laeufe.get(mandant_id)
        if ist_faellig(lauf, slot, jetzt, s.scheduler_retry_minuten):
            _pruefe_verzug(job, lauf, slot, s.scheduler_nachholen_max_tage)
            ergebnis.append(mandant_id)
    return ergebnis


async def _fehlgeschlagen(job: str, mandant_id: UUID | None, exc: Exception, jetzt: datetime) -> None:
    # Nur Typ und Kurztext: der Text steht in job_laeufe und damit im Health-Endpunkt.
    async with system_session() as session:
        await markiere_lauf(session, job, mandant_id, erfolg=False, fehler=f"{type(exc).__name__}: {exc}", jetzt=jetzt)


async def _fuehre_taeglichen_job(job: str, funktion: MandantenJob, jetzt: datetime) -> dict | None:
    async with system_session() as session:
        ids = await faellige_mandanten(session, job, jetzt)
    if not ids:
        return None

    with job_kontext(job):
        try:
            gesamt = await funktion(ids)
        except Exception as exc:
            logger.exception("Job %s fehlgeschlagen", job)
            if len(ids) == 1:
                await _fehlgeschlagen(job, ids[0], exc, jetzt)
                return {"mandanten": 1, "fehler": 1}
        else:
            async with system_session() as session:
                for mandant_id in ids:
                    await markiere_lauf(session, job, mandant_id, erfolg=True, ergebnis=gesamt, jetzt=jetzt)
            logger.info("Job %s fuer %d Mandant(en) abgeschlossen: %s", job, len(ids), gesamt)
            return {"mandanten": len(ids), "ergebnis": gesamt}

    # Sammel-Lauf gescheitert: einzeln wiederholen, damit ein defekter Mandant die uebrigen nicht blockiert.
    fehler = 0
    for mandant_id in ids:
        with job_kontext(job, mandant_id):
            try:
                einzel = await funktion([mandant_id])
            except Exception as exc:
                fehler += 1
                logger.exception("Job %s fuer Mandant %s fehlgeschlagen", job, mandant_id)
                await _fehlgeschlagen(job, mandant_id, exc, jetzt)
            else:
                async with system_session() as session:
                    await markiere_lauf(session, job, mandant_id, erfolg=True, ergebnis=einzel, jetzt=jetzt)
    return {"mandanten": len(ids), "einzeln": True, "fehler": fehler}


async def _fuehre_systemjob(job: str, funktion: SystemJob, takt: str, jetzt: datetime) -> bool:
    s = get_settings()
    slot = (
        jetzt.replace(minute=0, second=0, microsecond=0)
        if takt == "stuendlich"
        else letzter_slot(jetzt, s.scheduler_default_stunde_utc)
    )
    async with system_session() as session:
        lauf = (await lade_laeufe(session, job)).get(None)
    if not ist_faellig(lauf, slot, jetzt, s.scheduler_retry_minuten):
        return False
    _pruefe_verzug(job, lauf, slot, s.scheduler_nachholen_max_tage)
    with job_kontext(job):
        try:
            ergebnis = await funktion()
        except Exception as exc:
            logger.exception("Job %s fehlgeschlagen", job)
            await _fehlgeschlagen(job, None, exc, jetzt)
            return False
        async with system_session() as session:
            await markiere_lauf(session, job, None, erfolg=True, ergebnis=ergebnis if isinstance(ergebnis, dict) else None, jetzt=jetzt)
        if ergebnis:
            logger.info("Job %s abgeschlossen: %s", job, ergebnis)
    return True


async def fuehre_tick(jetzt: datetime | None = None) -> dict:
    """Ein Durchlauf: alle faelligen Jobs. Mehrfach-Worker-sicher; `jetzt` nur fuer Tests (simulierte Uhr)."""
    jetzt = jetzt or datetime.now(timezone.utc)
    async with worker_lock() as erlangt:
        if not erlangt:
            # Ein anderer Worker fuehrt gerade den Tick aus; der Zustand in der DB, nicht der Timer,
            # bestimmt beim naechsten Tick, was noch offen ist.
            logger.debug("Ein anderer Worker haelt den Lock, Tick uebersprungen")
            return {"lock": False}

        ausgefuehrt: dict[str, object] = {}
        for name, (funktion, takt) in SYSTEM_JOBS.items():
            if await _fuehre_systemjob(name, funktion, takt, jetzt):
                ausgefuehrt[name] = True
        for name, funktion in TAEGLICHE_JOBS.items():
            ergebnis = await _fuehre_taeglichen_job(name, funktion, jetzt)
            if ergebnis is not None:
                ausgefuehrt[name] = ergebnis
        return {"lock": True, "jobs": ausgefuehrt}
