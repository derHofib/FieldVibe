"""Docker-HEALTHCHECK-Helfer, nur Standardbibliothek (schneller Start, keine
Settings-Validierung):

    python -m app.healthcheck backend   # GET /health/ready auf localhost
    python -m app.healthcheck worker    # Alter der Heartbeat-Datei

Exit 0 = gesund, 1 = nicht gesund.
"""
import os
import sys
import time
import urllib.request

DATEI_STANDARD = "/tmp/fieldvibe-worker-heartbeat"
WORKER_MAX_ALTER_SEKUNDEN = 120


def pruefe_backend(url: str = "http://127.0.0.1:8000/health/ready") -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as antwort:
            return antwort.status == 200
    except Exception:
        return False


def pruefe_worker(datei: str | None = None, max_alter: int = WORKER_MAX_ALTER_SEKUNDEN) -> bool:
    datei = datei or os.environ.get("WORKER_HEARTBEAT_DATEI", DATEI_STANDARD)
    try:
        return time.time() - os.stat(datei).st_mtime <= max_alter
    except OSError:
        return False


def main(argv: list[str]) -> int:
    ziel = argv[0] if argv else ""
    if ziel == "backend":
        return 0 if pruefe_backend() else 1
    if ziel == "worker":
        return 0 if pruefe_worker() else 1
    print("Usage: python -m app.healthcheck backend|worker", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
