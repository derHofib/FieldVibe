"""Zentrale Logging-Konfiguration (JSON oder Text) und Log-Kontext.

Der Kontext (request_id, mandant_id, user_id, job) liegt in einem veraenderlichen
Dict in einer ContextVar: die Auth-Abhaengigkeit laeuft je nach Endpunkt in einem
kopierten Kontext (Threadpool), eine Zuweisung an die ContextVar selbst waere
dort fuer die Middleware unsichtbar -- das gemeinsame Dict nicht.
"""
import json
import logging
import re
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

_kontext: ContextVar[dict | None] = ContextVar("log_kontext", default=None)

_KONTEXT_FELDER = ("request_id", "mandant_id", "user_id", "job")
# Felder, die Aufrufer per `extra=` mitgeben duerfen (Access-Log). Alles andere
# am LogRecord wird bewusst NICHT ausgegeben -- so landen Bodies, Header oder
# Tokens nie versehentlich im Log.
_EXTRA_FELDER = ("method", "path", "status", "duration_ms", "event")

# Letzte Verteidigungslinie, falls ein Fremdmodul Zugangsdaten in eine Meldung
# schreibt (z. B. eine Exception mit URL samt Passwort).
_GEHEIM_MUSTER = re.compile(
    r"(?i)\b(authorization|cookie|set-cookie|password|passwort|passwd|secret|token|api[_-]?key|iban)"
    r"(\"?\s*[=:]\s*\"?)(?:bearer\s+)?[^\s\"',;&]+"
)
_URL_ZUGANG = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://[^/\s:@]+):[^@\s/]+@")


def schwaerze(text: str) -> str:
    text = _GEHEIM_MUSTER.sub(lambda m: f"{m.group(1)}{m.group(2)}[redacted]", text)
    return _URL_ZUGANG.sub(r"\1:[redacted]@", text)


def kontext_holen() -> dict:
    return _kontext.get() or {}


def kontext_neu(**werte) -> dict:
    """Setzt einen frischen Kontext fuer die aktuelle Task (Request, Job)."""
    kontext = {k: v for k, v in werte.items() if v is not None}
    _kontext.set(kontext)
    return kontext


def kontext_ergaenzen(**werte) -> None:
    kontext = _kontext.get()
    if kontext is None:
        kontext = {}
        _kontext.set(kontext)
    for key, value in werte.items():
        if value is not None:
            kontext[key] = str(value)


@contextmanager
def job_kontext(job: str, mandant_id=None):
    """Worker: Log-Zeilen innerhalb des Blocks tragen den Job-Namen."""
    token = _kontext.set({"job": job, **({"mandant_id": str(mandant_id)} if mandant_id else {})})
    try:
        yield
    finally:
        _kontext.reset(token)


class KontextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in kontext_holen().items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        eintrag: dict = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": schwaerze(record.getMessage()),
        }
        for key in (*_KONTEXT_FELDER, *_EXTRA_FELDER):
            wert = getattr(record, key, None)
            if wert is not None:
                eintrag[key] = wert
        if record.exc_info:
            eintrag["exc"] = schwaerze(self.formatException(record.exc_info))
        return json.dumps(eintrag, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        zusatz = " ".join(
            f"{key}={getattr(record, key)}" for key in _KONTEXT_FELDER if getattr(record, key, None) is not None
        )
        zeile = f"{self.formatTime(record, '%Y-%m-%d %H:%M:%S')} {record.levelname} {record.name}: " \
                f"{schwaerze(record.getMessage())}"
        if zusatz:
            zeile += f" [{zusatz}]"
        if record.exc_info:
            zeile += "\n" + schwaerze(self.formatException(record.exc_info))
        return zeile


def konfiguriere_logging(*, format: str, level: str = "INFO") -> None:
    """Idempotent: ersetzt die Handler des Root-Loggers und haengt die
    uvicorn-Logger daran. uvicorn.access wird stillgelegt -- Zugriffe schreibt
    die Request-Middleware (mit Request-ID, ohne Query-String)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if format == "json" else TextFormatter())
    handler.addFilter(KontextFilter())

    root = logging.getLogger()
    for alt in list(root.handlers):
        root.removeHandler(alt)
    root.addHandler(handler)
    root.setLevel(level.upper())

    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    zugriff = logging.getLogger("uvicorn.access")
    zugriff.handlers.clear()
    zugriff.propagate = False
    zugriff.disabled = True
