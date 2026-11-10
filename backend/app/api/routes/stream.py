import asyncio
import time
from datetime import datetime
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.api.deps import AuthContext, get_current_user, token_version_gueltig
from app.core.rollen import MITARBEITER_ROLLEN, ist_mitarbeiter_account
from app.core.security import TokenType, create_stream_ticket, decode_token
from app.db.session import system_session
from app.models.user import User
from app.services.event_bus import event_bus

router = APIRouter(prefix="/api/stream", tags=["stream"])




_PRUEFINTERVALL_SEKUNDEN = 15


async def _ticket_noch_gueltig(user_id: UUID, tv: int) -> bool:
    async with system_session() as session:
        row = (
            await session.execute(
                select(User.token_version, User.aktiv).where(User.id == user_id)
            )
        ).one_or_none()
    return row is not None and row.aktiv and row.token_version == tv


class StreamTicket(BaseModel):
    ticket: str
    gueltig_bis: datetime


@router.post("/ticket", response_model=StreamTicket)
async def stream_ticket(auth: AuthContext = Depends(get_current_user)) -> StreamTicket:
    """Tauscht das Bearer-Token gegen ein 60-s-Ticket fuer GET /api/stream.
    So landet nie ein Langzeit-Token in Query-String/Access-Logs. Einmal-
    verwendung wird bewusst nicht erzwungen (bei Mehr-Worker-Betrieb braeuchte
    sie gemeinsamen Speicher); das Ticket oeffnet nur den Stream, ist 60 s
    gueltig und an User + token_version gebunden."""
    if not ist_mitarbeiter_account(auth):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Keine Berechtigung")
    if auth.mandant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Kein Mandant im Token")
    ticket, gueltig_bis = create_stream_ticket(
        subject=auth.user_id,
        role=auth.role,
        mandant_id=auth.mandant_id,
        token_version=auth.token_version,
    )
    return StreamTicket(ticket=ticket, gueltig_bis=gueltig_bis)


@router.get("")
async def stream(request: Request, ticket: str | None = Query(None)) -> EventSourceResponse:
    # EventSource (the browser SSE client) cannot set an Authorization
    # header, so a short-lived ticket (POST /api/stream/ticket) travels as a
    # query param instead -- never an access token.
    # Fehlendes Ticket (z. B. altes Frontend mit ?token=) ist 401, nicht 422.
    if not ticket:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ticket fehlt")
    try:
        payload = decode_token(ticket)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültiges Ticket"
        ) from exc

    if payload.get("type") != TokenType.STREAM.value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültiges Ticket")
    if payload.get("role") not in MITARBEITER_ROLLEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Keine Berechtigung")
    if not payload.get("mandant_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Kein Mandant im Ticket")
    user_id = UUID(payload["sub"])
    await token_version_gueltig(User, user_id, payload, tv_pflicht=True)

    mandant_id = UUID(payload["mandant_id"])
    queue = event_bus.subscribe(mandant_id)

    async def event_generator():
        letzte_pruefung = time.monotonic()
        try:
            while True:
                if await request.is_disconnected():
                    break
                # Widerruf/Deaktivierung beendet auch eine offene Verbindung;
                # zeitbasiert statt nur beim Ping, damit regelmaessige Events
                # die Pruefung nicht aufschieben.
                if time.monotonic() - letzte_pruefung >= _PRUEFINTERVALL_SEKUNDEN:
                    letzte_pruefung = time.monotonic()
                    if not await _ticket_noch_gueltig(user_id, payload["tv"]):
                        break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                    yield item
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            event_bus.unsubscribe(mandant_id, queue)

    return EventSourceResponse(event_generator())
