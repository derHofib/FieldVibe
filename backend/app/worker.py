"""Hintergrund-Worker. Drei unabhaengige Schleifen:

- Scheduler: prueft jede Minute (scheduler_tick_sekunden), welche Jobs faellig sind
  (app/services/job_runner.py). Faellig heisst "letzter erfolgreicher Lauf liegt vor dem
  juengsten Slot" -- ein verpasster Lauf (Neustart, Ausfall) wird beim naechsten Tick
  nachgeholt, nicht erst am naechsten Tag. Enthalten: Pruefzyklen, Dauerauftraege,
  Prioritaet, Wiedervorlage, Angebot-Nachfassen, Mahnwesen, Kreditoren (je zur
  Scheduler-Stunde des Mandanten) sowie E-Mail-Rechnungseingang und Aufraeumen.
- Mail-Sync: persoenliche Postfaecher (siehe mail_sync_service.py) in eigenem, kurzem
  Takt -- eine Stunde Verzoegerung waere fuer einen Outlook-Ersatz spuerbar schlecht,
  echtes IMAP IDLE ist fuer V1 bewusst zurueckgestellt.
- Heartbeat: Lebenszeichen fuer Docker-Healthcheck und /health/heartbeats
  (app/services/heartbeat_service.py).

Laeuft als eigener Compose-Service (siehe docker-compose.yml, Service
"worker") -- getrennt vom Backend-Container, damit ein API-Neustart/Deploy
den Scheduler-Takt nicht stört und umgekehrt ein hängender Scheduler-Lauf
nie die API blockiert.

Usage:
    docker compose run --rm worker python -m app.worker
"""
import asyncio
import logging

from app.core.config import get_settings
from app.core.error_tracking import init_error_tracking
from app.core.logging_config import job_kontext, konfiguriere_logging
from app.db.rollen_pruefung import pruefe_db_rolle
from app.db.session import engine
from app.services.export_job_service import raeume_auf as raeume_exporte_auf
from app.services.export_job_service import verarbeite_naechsten as verarbeite_export
from app.services.heartbeat_service import heartbeat_schleife
from app.services.job_runner import fuehre_tick
from app.services.job_state_service import heartbeat
from app.services.mail_sync_service import run_mail_sync
from app.services.s3_aufraeumen_service import verarbeite as verarbeite_s3_aufraeumen
from app.services.worker_lock import mail_sync_lock

konfiguriere_logging(format=get_settings().log_format_aktiv, level=get_settings().log_level)
logger = logging.getLogger("app.worker")

MAIL_SYNC_INTERVAL_SECONDS = 120
# Mandanten-Exporte (Vollexport, Z3) starten nach dem Anfordern sofort im API-Prozess; der
# Worker holt liegengebliebene Auftraege (Neustart, Absturz) in diesem Takt nach.
EXPORT_INTERVAL_SECONDS = 30
# Aufraeumen abgelaufener Export-ZIPs und offener S3-Loeschauftraege (nach endgueltigem Loeschen);
# der API-Prozess erledigt die meisten sofort, das hier holt Fehlschlaege nach.
AUFRAEUM_ALLE_N_EXPORT_TAKTE = 20


async def _run_mail_sync_tick() -> None:
    async with mail_sync_lock() as acquired:
        if not acquired:
            # Ein anderer Worker-Container synchronisiert Postfaecher gerade
            # bereits -- der naechste Takt (siehe MAIL_SYNC_INTERVAL_SECONDS)
            # holt das nach.
            return
        with job_kontext("mail_sync"):
            try:
                ergebnis = await run_mail_sync()
                await heartbeat("mail_sync")
                if ergebnis["konten_synchronisiert"] or ergebnis["fehler"]:
                    logger.info("Mail-Sync abgeschlossen: %s", ergebnis)
            except Exception:
                logger.exception("Mail-Sync-Tick fehlgeschlagen")


async def _scheduler_loop() -> None:
    # Sofort ein erster Tick: nach einem Neustart/Deploy wird Versaeumtes unmittelbar nachgeholt.
    while True:
        try:
            await fuehre_tick()
        except Exception:
            logger.exception("Scheduler-Tick fehlgeschlagen")
        await asyncio.sleep(get_settings().scheduler_tick_sekunden)


async def _mail_sync_loop() -> None:
    while True:
        await asyncio.sleep(MAIL_SYNC_INTERVAL_SECONDS)
        await _run_mail_sync_tick()


async def _export_loop() -> None:
    takt = 0
    while True:
        await asyncio.sleep(EXPORT_INTERVAL_SECONDS)
        try:
            while await verarbeite_export() is not None:
                pass
        except Exception:
            logger.exception("Export-Verarbeitung fehlgeschlagen")
        takt += 1
        if takt % AUFRAEUM_ALLE_N_EXPORT_TAKTE:
            continue
        try:
            entfernt = await raeume_exporte_auf()
            if entfernt:
                logger.info("Export-Aufräumen: %d abgelaufene(s) Ergebnis-ZIP entfernt", entfernt)
        except Exception:
            logger.exception("Export-Aufräumen fehlgeschlagen")
        try:
            s3_ergebnis = await verarbeite_s3_aufraeumen()
            if s3_ergebnis["erledigt"] or s3_ergebnis["fehlgeschlagen"]:
                logger.info("S3-Aufräumen: %s", s3_ergebnis)
        except Exception:
            logger.exception("S3-Aufräumen fehlgeschlagen")


async def main() -> None:
    init_error_tracking(komponente="worker")
    await pruefe_db_rolle(engine)
    logger.info(
        "Worker gestartet -- Scheduler-Tick alle %d Sekunden, Mail-Sync alle %d Sekunden",
        get_settings().scheduler_tick_sekunden, MAIL_SYNC_INTERVAL_SECONDS,
    )
    await asyncio.gather(_scheduler_loop(), _mail_sync_loop(), _export_loop(), heartbeat_schleife())


if __name__ == "__main__":
    asyncio.run(main())
