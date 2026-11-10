"""Lebenszeichen des Workers: Datei (Docker-Healthcheck), Zeile in job_laeufe
(Auswertung durch das Backend) und optionaler externer Ping (healthchecks.io-
kompatibel, GET <url>).

Die Schleife laeuft im selben Event-Loop wie die Jobs: haengt der Loop (blockierender
Aufruf), bleibt das Lebenszeichen aus -- genau das soll der Check bemerken.
"""
import asyncio
import logging
import os
import time
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.services.job_state_service import heartbeat

logger = logging.getLogger("app.heartbeat")

WORKER_JOB = "worker_tick"


def schreibe_heartbeat_datei(pfad: str) -> None:
    datei = Path(pfad)
    tmp = datei.with_name(datei.name + ".tmp")
    tmp.write_text(str(int(time.time())), encoding="utf-8")
    os.replace(tmp, datei)


async def pinge_extern(url: str) -> bool:
    """Best effort: ein ausbleibender Ping loest beim Dienst den Alarm aus, ein
    Fehler hier darf den Worker nie stoeren."""
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
            antwort = await client.get(url)
        return antwort.status_code < 400
    except Exception as exc:
        # Nur der Typ: die Ping-URL enthaelt ein Geheimnis (UUID) und steht oft in der Exception.
        logger.warning("Heartbeat-Ping fehlgeschlagen (%s)", type(exc).__name__)
        return False


async def heartbeat_einmal(*, letzter_ping: float | None) -> float | None:
    """Ein Durchlauf; gibt den Zeitpunkt des letzten Pings zurueck (Takt eigener Intervall)."""
    s = get_settings()
    try:
        schreibe_heartbeat_datei(s.worker_heartbeat_datei)
    except OSError as exc:
        logger.warning("Heartbeat-Datei nicht schreibbar (%s)", type(exc).__name__)
    try:
        await heartbeat(WORKER_JOB)
    except Exception:
        logger.exception("Heartbeat konnte nicht in die Datenbank geschrieben werden")
    jetzt = time.monotonic()
    if s.heartbeat_ping_url and (letzter_ping is None or jetzt - letzter_ping >= s.heartbeat_ping_intervall_sekunden):
        await pinge_extern(s.heartbeat_ping_url)
        return jetzt
    return letzter_ping


async def heartbeat_schleife() -> None:
    letzter_ping: float | None = None
    while True:
        letzter_ping = await heartbeat_einmal(letzter_ping=letzter_ping)
        await asyncio.sleep(get_settings().heartbeat_intervall_sekunden)
