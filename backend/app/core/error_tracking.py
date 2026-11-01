"""Optionales Error-Tracking (Sentry-kompatibel, z. B. selbst gehostetes GlitchTip).

Ohne SENTRY_DSN passiert nichts: das SDK wird nicht importiert und es entsteht
kein Netzverkehr. Mit DSN gilt Datenschutz zuerst: keine PII, keine Request-
Bodies, keine Query-Strings (Reset-Links tragen Tokens), keine Header ausser
einer kleinen Positivliste, keine SQL-Breadcrumbs, Geheimnisse im Text werden
geschwaerzt. Nur EU-gehostet/selbst betrieben einsetzen (AVV, docs/BETRIEB.md).
"""
import logging
from typing import Any

from app.core.config import get_settings
from app.core.logging_config import kontext_holen, schwaerze

logger = logging.getLogger("app.error_tracking")

# Positivliste: alles andere (authorization, cookie, x-api-key, ...) fliegt raus.
_ERLAUBTE_HEADER = frozenset({"content-type", "content-length", "user-agent", "accept", "x-request-id", "host"})
_ZUSAETZLICHE_DENYLIST = [
    "authorization", "cookie", "iban", "bic", "passwort", "kennwort", "pin", "refresh", "csrf",
    "mfa", "otp", "email", "e-mail",
]


def _schwaerze_text(wert: Any) -> Any:
    return schwaerze(wert) if isinstance(wert, str) else wert


def scrub_event(event: dict, hint: dict | None = None) -> dict | None:
    """before_send: letzte Reinigung, unabhaengig von den SDK-Voreinstellungen."""
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        request.pop("query_string", None)
        url = request.get("url")
        if isinstance(url, str):
            request["url"] = url.split("?", 1)[0].split("#", 1)[0]
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {k: v for k, v in headers.items() if k.lower() in _ERLAUBTE_HEADER}
        request.pop("env", None)
    event.pop("user", None)
    event.pop("server_name", None)

    for exc in (event.get("exception") or {}).get("values", []) or []:
        exc["value"] = _schwaerze_text(exc.get("value"))
        # Lokale Variablen koennen alles enthalten; include_local_variables ist aus,
        # hier zur Sicherheit trotzdem entfernen.
        for frame in (exc.get("stacktrace") or {}).get("frames", []) or []:
            frame.pop("vars", None)
    if isinstance(event.get("message"), str):
        event["message"] = _schwaerze_text(event["message"])
    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        logentry["message"] = _schwaerze_text(logentry.get("message"))
        if "formatted" in logentry:
            logentry["formatted"] = _schwaerze_text(logentry["formatted"])
        logentry.pop("params", None)
    extra = event.get("extra")
    if isinstance(extra, dict):
        extra.pop("sys.argv", None)

    breadcrumbs = event.get("breadcrumbs")
    if isinstance(breadcrumbs, dict):
        werte = [b for b in breadcrumbs.get("values", []) if b.get("category") not in ("query", "httplib")]
        for b in werte:
            b["message"] = _schwaerze_text(b.get("message"))
            b.pop("data", None)
        breadcrumbs["values"] = werte

    tags = event.setdefault("tags", {})
    for key in ("request_id", "mandant_id", "job"):
        wert = kontext_holen().get(key)
        if wert:
            tags[key] = wert
    return event


def scrub_breadcrumb(crumb: dict, hint: dict | None = None) -> dict | None:
    if crumb.get("category") in ("query", "httplib"):
        return None
    crumb["message"] = _schwaerze_text(crumb.get("message"))
    crumb.pop("data", None)
    return crumb


def init_error_tracking(*, komponente: str, transport: Any = None) -> bool:
    """Initialisiert das SDK, falls SENTRY_DSN gesetzt ist. `transport` nur fuer Tests."""
    s = get_settings()
    if not s.sentry_dsn or not s.sentry_dsn.strip():
        return False

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration, ignore_logger
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration
    from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber

    sentry_sdk.init(
        dsn=s.sentry_dsn.strip(),
        release=s.sentry_release or s.git_commit,
        environment=s.sentry_environment or s.environment,
        sample_rate=s.sentry_sample_rate,
        traces_sample_rate=s.sentry_traces_sample_rate,
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
        include_source_context=False,
        server_name="",
        event_scrubber=EventScrubber(denylist=[*DEFAULT_DENYLIST, *_ZUSAETZLICHE_DENYLIST], recursive=True),
        before_send=scrub_event,
        before_breadcrumb=scrub_breadcrumb,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
            SqlalchemyIntegration(),
            # Fehler-Logs (logger.exception) werden Events; INFO/WARNING nur Breadcrumb-Text.
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        **({"transport": transport} if transport is not None else {}),
    )
    # Das Zugriffs-Log meldet 5xx auf ERROR-Ebene; der Fehler selbst kommt schon als
    # Exception-Event, ein zweites Event je Request waere nur Dopplung.
    ignore_logger("app.access")
    sentry_sdk.set_tag("komponente", komponente)
    logger.info("Error-Tracking aktiv (Komponente %s, Release %s)", komponente, s.sentry_release or s.git_commit)
    return True
