from app.models.vorgang_event import VorgangEvent
from app.schemas.vorgang_event import VorgangEventRead
from app.services import storage_service


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
