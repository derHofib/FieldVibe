"""Hintergrund-Worker: führt den Prüfzyklen-Scheduler einmal täglich aus.

Läuft als eigener Compose-Service (siehe docker-compose.yml, Service
"worker") -- getrennt vom Backend-Container, damit ein API-Neustart/Deploy
den Scheduler-Takt nicht stört und umgekehrt ein hängender Scheduler-Lauf
nie die API blockiert.

Usage:
    docker compose run --rm worker python -m app.worker
"""
import asyncio
import logging
from datetime import datetime, time, timedelta, timezone

from app.services.scheduler_service import run_pruefzyklen_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("app.worker")

# Nachts, wenn kein Techniker aktiv im Feed arbeitet -- automatisch
# angelegte Vorgaenge tauchen dann am naechsten Morgen frisch im Feed auf.
LAUFZEIT_UTC = time(hour=3, minute=0)


def _seconds_until_next_run(now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    target = datetime.combine(now.date(), LAUFZEIT_UTC, tzinfo=timezone.utc)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def main() -> None:
    logger.info("Prüfzyklen-Scheduler-Worker gestartet (täglich %s UTC)", LAUFZEIT_UTC)
    while True:
        wartezeit = _seconds_until_next_run()
        logger.info("Nächster Lauf in %.0f Sekunden", wartezeit)
        await asyncio.sleep(wartezeit)
        try:
            ergebnis = await run_pruefzyklen_scheduler()
            logger.info("Scheduler-Lauf abgeschlossen: %s", ergebnis)
        except Exception:
            logger.exception("Scheduler-Lauf fehlgeschlagen")


if __name__ == "__main__":
    asyncio.run(main())
