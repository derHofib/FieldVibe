"""Request-ID und Zugriffs-Log als reine ASGI-Middleware.

Bewusst kein BaseHTTPMiddleware: das puffert/entkoppelt Antworten und braeche
den SSE-Stream (app/api/routes/stream.py).
"""
import logging
import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging_config import kontext_holen, kontext_neu

REQUEST_ID_HEADER = "X-Request-ID"
# Eingehende IDs (z. B. vom Proxy) nur uebernehmen, wenn sie unverfaenglich sind
# -- sonst liessen sich beliebige Zeichen (Zeilenumbrueche, Markup) ins Log schleusen.
_GUELTIGE_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
# Health-Checks im Sekundentakt wuerden das Log fluten.
_NICHT_PROTOKOLLIEREN = frozenset({"/health", "/health/ready", "/healthz"})

zugriff_logger = logging.getLogger("app.access")


class RequestKontextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        eingehend = next(
            (v.decode("latin-1") for k, v in scope["headers"] if k == b"x-request-id"), None
        )
        request_id = eingehend if eingehend and _GUELTIGE_ID.match(eingehend) else uuid.uuid4().hex
        kontext_neu(request_id=request_id)
        scope.setdefault("state", {})["request_id"] = request_id

        status_code = 500
        start = time.perf_counter()

        async def send_mit_id(nachricht: Message) -> None:
            nonlocal status_code
            if nachricht["type"] == "http.response.start":
                status_code = nachricht["status"]
                MutableHeaders(scope=nachricht)[REQUEST_ID_HEADER] = request_id
            await send(nachricht)

        try:
            await self.app(scope, receive, send_mit_id)
        finally:
            if scope["path"] not in _NICHT_PROTOKOLLIEREN:
                # Routen-Vorlage statt echtem Pfad: Pfadsegmente koennen Tokens
                # oder IDs enthalten (Reset-Links, Portal-Slugs). Query-String
                # wird nie protokolliert.
                route = scope.get("route")
                pfad = getattr(route, "path", None) or scope["path"]
                zugriff_logger.log(
                    logging.ERROR if status_code >= 500 else logging.INFO,
                    "%s %s -> %d",
                    scope["method"], pfad, status_code,
                    extra={
                        # Explizit statt ueber den Handler-Filter: der Kontext soll
                        # auch an Handlern ohne KontextFilter ankommen.
                        **kontext_holen(),
                        "event": "http_request",
                        "method": scope["method"],
                        "path": pfad,
                        "status": status_code,
                        "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                    },
                )
