"""ASGI-Middleware: Request-ID und Client-IP fuers Audit-Protokoll bereitstellen.

Reine ASGI-Middleware statt BaseHTTPMiddleware, weil Letztere ContextVars nicht
zuverlaessig an den Endpunkt weitergibt. Die IP stammt aus scope["client"]; hinter
einem vertrauenswuerdigen Proxy hat Uvicorn sie bereits aus X-Forwarded-For
gesetzt (siehe rate_limit.client_ip) -- kein eigenes Header-Parsing."""
import uuid

from app.services import audit_service


class AuditKontextMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # Die Request-ID vergibt die aeussere RequestKontextMiddleware (Header und Log);
        # hier nur uebernehmen, damit Audit-Eintrag, Log und Antwort dieselbe ID tragen.
        request_id = scope.get("state", {}).get("request_id") or uuid.uuid4().hex
        client = scope.get("client")
        tokens = audit_service.kontext_setzen(request_id, client[0] if client else None)

        try:
            await self.app(scope, receive, send)
        finally:
            audit_service.kontext_zuruecksetzen(tokens)
