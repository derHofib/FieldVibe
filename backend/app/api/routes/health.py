"""Health-Endpunkte fuer Orchestrierung und Monitoring.

- GET /health            Liveness: Prozess lebt (kein I/O, immer billig).
- GET /health/ready      Bereitschaft: DB, Objektspeicher, Migrationsstand. Ohne
                         Ausweis nur Status + HTTP-Code, nie Details.
- GET /health/heartbeats Alter der Hintergrundjobs/Backups; nur mit Health-Token
                         oder als Plattform-Admin.
- GET /healthz           Altbestand (Docker-Healthcheck frueherer Stacks, Super-Admin-
                         Uebersicht): Antwortformat unveraendert.
"""
import hmac

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from app.api.deps import _auth_context_aus_token
from app.core.config import get_settings
from app.core.rollen import ist_plattform_admin
from app.db.session import engine
from app.services import health_service
from app.services.scheduler_service import get_last_scheduler_run
from app.services.storage_service import ensure_bucket

router = APIRouter(tags=["health"])
_bearer = HTTPBearer(auto_error=False)


async def _ist_berechtigt(credentials: HTTPAuthorizationCredentials | None) -> bool:
    if credentials is None:
        return False
    token = get_settings().health_token
    if token and hmac.compare_digest(credentials.credentials.encode(), token.encode()):
        return True
    try:
        auth = await _auth_context_aus_token(credentials, einrichtung_erlaubt=False)
    except (HTTPException, jwt.PyJWTError, ValueError, KeyError):
        return False
    return ist_plattform_admin(auth)


async def _erfordere_berechtigung(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    if not await _ist_berechtigt(credentials):
        # 404 statt 401/403: ohne Ausweis soll nicht auffallen, dass es den Pfad gibt.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def health_ready(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> JSONResponse:
    pruefungen = await health_service.bereitschaft()
    bereit = all(p.ok for p in pruefungen.values())
    inhalt: dict = {"status": "ok" if bereit else "nicht_bereit"}
    if await _ist_berechtigt(credentials):
        inhalt["pruefungen"] = {
            name: {"ok": p.ok, "detail": p.detail or None} for name, p in pruefungen.items()
        }
        inhalt["migration_head"] = health_service.alembic_head()
    return JSONResponse(inhalt, status_code=200 if bereit else status.HTTP_503_SERVICE_UNAVAILABLE)


@router.get("/health/heartbeats", dependencies=[Depends(_erfordere_berechtigung)])
async def health_heartbeats() -> JSONResponse:
    eintraege = await health_service.heartbeats()
    gesamt = health_service.gesamtstatus(eintraege)
    return JSONResponse(
        {"status": gesamt, "heartbeats": eintraege},
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE if gesamt == "fehler" else 200,
    )


@router.get("/healthz")
async def healthz() -> dict:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await ensure_bucket()
    letzter_scheduler_lauf = await get_last_scheduler_run()
    return {
        "status": "ok",
        "scheduler_letzter_lauf": letzter_scheduler_lauf.isoformat() if letzter_scheduler_lauf else None,
    }
