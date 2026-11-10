"""ASGI-Middleware: Request-ID und Client-IP fuers Audit-Protokoll bereitstellen.

Reine ASGI-Middleware statt BaseHTTPMiddleware, weil Letztere ContextVars nicht
zuverlaessig an den Endpunkt weitergibt. Die IP stammt aus scope["client"]; hinter
einem vertrauenswuerdigen Proxy hat Uvicorn sie bereits aus X-Forwarded-For
gesetzt (siehe rate_limit.client_ip) -- kein eigenes Header-Parsing."""
import re
import uuid

from app.services import audit_service

_ID_MUSTER = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class AuditKontextMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = None
        for name, wert in scope.get("headers", []):
            if name == b"x-request-id":
                kandidat = wert.decode("latin-1")
                if _ID_MUSTER.match(kandidat):
                    request_id = kandidat
                break
        request_id = request_id or uuid.uuid4().hex
        # Die innere RequestKontextMiddleware uebernimmt die ID und setzt den Antwort-Header,
        # damit Audit-Protokoll und Logs dieselbe ID tragen.
        scope.setdefault("state", {})["request_id"] = request_id
        client = scope.get("client")
        tokens = audit_service.kontext_setzen(request_id, client[0] if client else None)

        try:
            await self.app(scope, receive, send)
        finally:
            audit_service.kontext_zuruecksetzen(tokens)
