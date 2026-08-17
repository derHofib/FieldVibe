"""Hintergrund-Worker: prueft stuendlich, welche Mandanten gerade ihre
konfigurierte taegliche Scheduler-Stunde erreicht haben, und fuehrt fuer
genau diese den Pruefzyklen-Scheduler, die Mahnwesen-Eskalation und den
Kreditorenbuchhaltung-Faelligkeits-Check aus. Der E-Mail-Rechnungseingang-
Import (siehe email_ingest_service.py) laeuft dagegen unabhaengig von der
mandantenindividuellen Scheduler-Stunde bei jedem stuendlichen Tick fuer
alle Mandanten mit aktiver IMAP-Integration -- ein neuer Beleg soll nicht
bis zu 24 Stunden auf die naechste Verarbeitung warten.

Laeuft als eigener Compose-Service (siehe docker-compose.yml, Service
"worker") -- getrennt vom Backend-Container, damit ein API-Neustart/Deploy
den Scheduler-Takt nicht stört und umgekehrt ein hängender Scheduler-Lauf
nie die API blockiert.

Usage:
    docker compose run --rm worker python -m app.worker
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.db.session import system_session
from app.services.email_ingest_service import run_email_ingest
from app.services.kreditorenbuchhaltung_service import run_kreditoren_faelligkeits_check
from app.services.mahnwesen_service import run_mahnwesen_eskalation
from app.services.mail_sync_service import run_mail_sync
from app.services.scheduler_service import (
    mandanten_faellig_um,
    run_dauerauftraege_scheduler,
    run_prioritaet_scheduler,
    run_pruefzyklen_scheduler,
    run_wiedervorlage_scheduler,
)
from app.services.worker_lock import mail_sync_lock, worker_lock

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("app.worker")

# Persoenliche Postfaecher (siehe mail_sync_service.py) laufen in einem
# eigenen, viel kuerzeren Takt als der stuendliche Scheduler-Tick -- eine
# Stunde Verzoegerung waere fuer einen Outlook-Ersatz spuerbar schlecht,
# echtes IMAP IDLE (Server-Push) ist fuer V1 bewusst zurueckgestellt.
MAIL_SYNC_INTERVAL_SECONDS = 120


def _seconds_until_next_full_hour(now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return (next_hour - now).total_seconds()


async def _run_hourly_tick() -> None:
    jetzt = datetime.now(timezone.utc)
    async with system_session() as session:
        mandant_ids = await mandanten_faellig_um(session, jetzt.hour)

    async with worker_lock() as acquired:
        if not acquired:
            # Ein anderer Worker-Container haelt den Lock bereits fuer
            # diesen Tick -- kein Grund zur Sorge, der naechste stuendliche
            # Tick greift wieder (der Zustand in der DB, nicht der Timer,
            # ist die Quelle der Wahrheit dafuer, was faellig ist).
            logger.info("Ein anderer Worker hält den Lock bereits, dieser Tick wird übersprungen")
            return

        try:
            email_ergebnis = await run_email_ingest()
            logger.info("E-Mail-Rechnungseingang-Import abgeschlossen: %s", email_ergebnis)
        except Exception:
            logger.exception("E-Mail-Rechnungseingang-Import fehlgeschlagen")

        if not mandant_ids:
            logger.info("Keine Mandanten für Stunde %02d:00 UTC fällig", jetzt.hour)
            return

        try:
            ergebnis = await run_pruefzyklen_scheduler(mandant_ids)
            logger.info(
                "Scheduler-Lauf (Stunde %02d:00 UTC, %d Mandant(en)) abgeschlossen: %s",
                jetzt.hour, len(mandant_ids), ergebnis,
            )
        except Exception:
            logger.exception("Scheduler-Lauf fehlgeschlagen")

        try:
            dauerauftraege_ergebnis = await run_dauerauftraege_scheduler(mandant_ids)
            logger.info(
                "Dauerauftraege-Lauf (Stunde %02d:00 UTC, %d Mandant(en)) abgeschlossen: %s",
                jetzt.hour, len(mandant_ids), dauerauftraege_ergebnis,
            )
        except Exception:
            logger.exception("Dauerauftraege-Lauf fehlgeschlagen")

        try:
            prioritaet_ergebnis = await run_prioritaet_scheduler(mandant_ids)
            logger.info(
                "Prioritaets-Lauf (Stunde %02d:00 UTC, %d Mandant(en)) abgeschlossen: %s",
                jetzt.hour, len(mandant_ids), prioritaet_ergebnis,
            )
        except Exception:
            logger.exception("Prioritaets-Lauf fehlgeschlagen")

        try:
            wiedervorlage_ergebnis = await run_wiedervorlage_scheduler(mandant_ids)
            logger.info(
                "Wiedervorlage-Lauf (Stunde %02d:00 UTC, %d Mandant(en)) abgeschlossen: %s",
                jetzt.hour, len(mandant_ids), wiedervorlage_ergebnis,
            )
        except Exception:
            logger.exception("Wiedervorlage-Lauf fehlgeschlagen")

        try:
            mahn_ergebnis = await run_mahnwesen_eskalation(mandant_ids)
            logger.info(
                "Mahnwesen-Lauf (Stunde %02d:00 UTC, %d Mandant(en)) abgeschlossen: %s",
                jetzt.hour, len(mandant_ids), mahn_ergebnis,
            )
        except Exception:
            logger.exception("Mahnwesen-Lauf fehlgeschlagen")

        try:
            kreditoren_ergebnis = await run_kreditoren_faelligkeits_check(mandant_ids)
            logger.info(
                "Kreditorenbuchhaltung-Lauf (Stunde %02d:00 UTC, %d Mandant(en)) abgeschlossen: %s",
                jetzt.hour, len(mandant_ids), kreditoren_ergebnis,
            )
        except Exception:
            logger.exception("Kreditorenbuchhaltung-Lauf fehlgeschlagen")


async def _run_mail_sync_tick() -> None:
    async with mail_sync_lock() as acquired:
        if not acquired:
            # Ein anderer Worker-Container synchronisiert Postfaecher gerade
            # bereits -- der naechste Takt (siehe MAIL_SYNC_INTERVAL_SECONDS)
            # holt das nach.
            return
        try:
            ergebnis = await run_mail_sync()
            if ergebnis["konten_synchronisiert"] or ergebnis["fehler"]:
                logger.info("Mail-Sync abgeschlossen: %s", ergebnis)
        except Exception:
            logger.exception("Mail-Sync-Tick fehlgeschlagen")


async def _hourly_loop() -> None:
    while True:
        wartezeit = _seconds_until_next_full_hour()
        logger.info("Nächster stündlicher Tick in %.0f Sekunden", wartezeit)
        await asyncio.sleep(wartezeit)
        try:
            await _run_hourly_tick()
        except Exception:
            logger.exception("Stündlicher Tick fehlgeschlagen")


async def _mail_sync_loop() -> None:
    while True:
        await asyncio.sleep(MAIL_SYNC_INTERVAL_SECONDS)
        await _run_mail_sync_tick()


async def main() -> None:
    logger.info(
        "Worker gestartet -- stündlicher Scheduler-Tick, Mail-Sync alle %d Sekunden",
        MAIL_SYNC_INTERVAL_SECONDS,
    )
    await asyncio.gather(_hourly_loop(), _mail_sync_loop())


if __name__ == "__main__":
    asyncio.run(main())
