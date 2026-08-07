import asyncio
from collections import deque
from datetime import datetime, timezone

import psutil

# 40 Samples alle 15s = 10 Minuten Verlauf fuer die Sparkline im Super-Admin-
# Dashboard. Bewusst nur im Prozessspeicher (kein Sparkline-Anspruch auf
# Ueberleben eines Neustarts) -- der Backend-Container laeuft laut
# docker-compose.yml mit genau einem uvicorn-Worker, es gibt also keine
# Inkonsistenz zwischen mehreren Prozessen mit je eigenem Ringpuffer.
SAMPLE_INTERVAL_SECONDS = 15
HISTORY_MAXLEN = 40

_history: deque[dict] = deque(maxlen=HISTORY_MAXLEN)


def _sample() -> dict:
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        # interval=None nutzt die Zeit seit dem letzten Aufruf als Basis --
        # dank der 15s-Schleife unten liefert das sinnvolle, nicht blockierende
        # Werte (der allererste Aufruf beim Start liefert 0.0, siehe unten).
        "cpu_percent": psutil.cpu_percent(interval=None),
        "ram_percent": ram.percent,
        "ram_used_mb": round(ram.used / (1024 * 1024)),
        "ram_total_mb": round(ram.total / (1024 * 1024)),
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / (1024 * 1024 * 1024), 1),
        "disk_total_gb": round(disk.total / (1024 * 1024 * 1024), 1),
    }


def get_current_and_history() -> dict:
    aktuell = _sample()
    return {"aktuell": aktuell, "verlauf": list(_history)}


async def resource_sampler_loop() -> None:
    # Erster Aufruf von psutil.cpu_percent(interval=None) direkt nach
    # Prozessstart liefert per Definition 0.0 (kein Vergleichszeitraum) --
    # daher hier einmal "verwerfen", bevor der Ringpuffer befuellt wird.
    psutil.cpu_percent(interval=None)
    while True:
        await asyncio.sleep(SAMPLE_INTERVAL_SECONDS)
        _history.append(_sample())
