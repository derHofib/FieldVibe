from typing import TYPE_CHECKING

from app.models.vorgang_event import VorgangEvent
from app.schemas.vorgang_event import VorgangEventRead
from app.services import storage_service

if TYPE_CHECKING:
    from app.api.deps import AuthContext


def to_read_model(event: VorgangEvent) -> VorgangEventRead:
    data = VorgangEventRead.model_validate(event)
    if event.event_type == "foto" and event.payload:
        key = event.payload.get("key")
        thumbnail_key = event.payload.get("thumbnail_key")
        if key:
            data.foto_url = storage_service.presigned_get_url(key)
        if thumbnail_key:
            data.foto_thumbnail_url = storage_service.presigned_get_url(thumbnail_key)
    elif event.event_type == "unterschrift" and event.payload:
        key = event.payload.get("key")
        if key:
            data.unterschrift_url = storage_service.presigned_get_url(key)
    elif event.event_type == "dokument" and event.payload:
        key = event.payload.get("key")
        if key:
            data.dokument_url = storage_service.presigned_get_url(key)
        data.dokument_dateiname = event.payload.get("dateiname")
    return data


def mit_ki_kennzeichnung(auth: "AuthContext", payload: dict | None = None) -> dict:
    """Payload fuer ein neues Event; bei Aufrufen ueber den MCP-Adapter mit der Kennzeichnung "via Claude".
    Gesetzt wird sie nur aus dem signierten Token, ein vom Client mitgeschickter Wert wird entfernt,
    damit sich niemand als KI ausgeben (oder die Kennzeichnung unterdruecken) kann."""
    ergebnis = {k: v for k, v in (payload or {}).items() if k not in ("via", "ki_verbindung_id")}
    if auth.via == "mcp":
        ergebnis["via"] = "claude"
        if auth.ki_verbindung_id is not None:
            ergebnis["ki_verbindung_id"] = str(auth.ki_verbindung_id)
    return ergebnis
