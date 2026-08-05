from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AuthContext,
    get_current_user,
    get_db,
    require_module,
    require_recht,
    require_roles,
)
from app.models.highlight import Highlight
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.highlight import HighlightCreate, HighlightRead
from app.services import storage_service
from app.services.rechte_service import hat_recht

router = APIRouter(
    prefix="/api/highlights",
    tags=["highlights"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("vorgaenge", "sehen")),
        Depends(require_module("highlights")),
    ],
)


async def _to_read_model(session: AsyncSession, highlight: Highlight) -> HighlightRead:
    event = await session.get(VorgangEvent, highlight.vorgang_event_id)
    vorgang = await session.get(Vorgang, event.vorgang_id)
    foto_url = None
    foto_thumbnail_url = None
    if event.payload:
        key = event.payload.get("key")
        thumbnail_key = event.payload.get("thumbnail_key")
        if key:
            foto_url = storage_service.presigned_get_url(key)
        if thumbnail_key:
            foto_thumbnail_url = storage_service.presigned_get_url(thumbnail_key)

    return HighlightRead(
        id=highlight.id,
        vorgang_event_id=highlight.vorgang_event_id,
        titel=highlight.titel,
        erstellt_von=highlight.erstellt_von,
        created_at=highlight.created_at,
        vorgang_id=vorgang.id,
        vorgangsnummer=vorgang.vorgangsnummer,
        vorgang_titel=vorgang.titel,
        foto_url=foto_url,
        foto_thumbnail_url=foto_thumbnail_url,
    )


@router.get("", response_model=list[HighlightRead])
async def list_highlights(session: AsyncSession = Depends(get_db)) -> list[HighlightRead]:
    result = await session.execute(select(Highlight).order_by(Highlight.created_at.desc()))
    return [await _to_read_model(session, h) for h in result.scalars().all()]


@router.post("", response_model=HighlightRead, status_code=status.HTTP_201_CREATED)
async def create_highlight(
    body: HighlightCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> HighlightRead:
    event = await session.get(VorgangEvent, body.vorgang_event_id)
    if event is None or event.event_type != "foto":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nur Foto-Events können als Highlight markiert werden",
        )

    highlight = Highlight(
        mandant_id=auth.mandant_id,
        vorgang_event_id=body.vorgang_event_id,
        titel=body.titel,
        erstellt_von=auth.user_id,
    )
    session.add(highlight)
    try:
        await session.flush()
    except IntegrityError as exc:
        # UniqueConstraint auf vorgang_event_id -- ein Foto ist entweder schon
        # markiert (dann reicht der bestehende Eintrag) oder es ist ein
        # echter Fehler; ein 409 ist fuer den Kunden-facing Highlight-Button
        # informativer als ein blanker 500.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Dieses Foto ist bereits ein Highlight"
        ) from exc
    return await _to_read_model(session, highlight)


@router.delete("/{highlight_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_highlight(
    highlight_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    highlight = await session.get(Highlight, highlight_id)
    if highlight is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Highlight nicht gefunden")
    # Account-Typen mit vorgaenge:loeschen duerfen jedes Highlight entfernen
    # (Moderation); alle anderen nur ihr eigenes.
    darf_alle_loeschen = auth.role == "mandant_admin" or (
        auth.role == "custom"
        and await hat_recht(
            session, account_typ_id=auth.account_typ_id, bereich="vorgaenge", aktion="loeschen"
        )
    )
    if not darf_alle_loeschen and highlight.erstellt_von != auth.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Nur eigene Highlights können entfernt werden"
        )
    await session.delete(highlight)
    await session.flush()
