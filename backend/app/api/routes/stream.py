import asyncio
from uuid import UUID

import jwt
from fastapi import APIRouter, HTTPException, Query, Request, status
from sse_starlette.sse import EventSourceResponse

from app.core.security import decode_token
from app.services.event_bus import event_bus

router = APIRouter(prefix="/api/stream", tags=["stream"])


@router.get("")
async def stream(request: Request, token: str = Query(...)) -> EventSourceResponse:
    # EventSource (the browser SSE client) cannot set an Authorization
    # header, so the access token travels as a query param here instead --
    # the one deliberate exception to the header-based auth used everywhere
    # else in this API.
    try:
        payload = decode_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültiges Token"
        ) from exc

    if payload.get("type") not in ("access", "impersonation"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültiges Token")
    if payload.get("role") not in ("mandant_admin", "custom"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Keine Berechtigung")
    if not payload.get("mandant_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Kein Mandant im Token")

    mandant_id = UUID(payload["mandant_id"])
    queue = event_bus.subscribe(mandant_id)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                    yield item
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            event_bus.unsubscribe(mandant_id, queue)

    return EventSourceResponse(event_generator())
