import base64
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.models.anlage import Anlage
from app.models.kunde import Kunde
from app.models.tag import Tag, TagAssignment
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.models.zeiterfassung import Zeiterfassung
from app.schemas.feed import FeedCard, FeedResponse

router = APIRouter(
    prefix="/api/feed",
    tags=["feed"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)

DEFAULT_PAGE_SIZE = 20

_EVENT_TYPE_PREVIEW = {
    "status_change": "Status geändert",
    "foto": "Foto hinzugefügt",
    "dokument": "Dokument hinzugefügt",
    "mangel": "Mangel erfasst",
    "angebot": "Angebot aktualisiert",
    "material": "Material erfasst",
    "zeit_start": "Zeit gestartet",
    "zeit_stop": "Zeit gestoppt",
    "termin": "Termin",
    "rechnung_status": "Rechnungsstatus aktualisiert",
    "system": "System-Ereignis",
}


def _encode_cursor(last_activity_at, id_: UUID) -> str:
    raw = f"{last_activity_at.isoformat()}|{id_}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        last_activity_at, id_ = raw.split("|", 1)
        return datetime.fromisoformat(last_activity_at), UUID(id_)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Ungültiger Cursor"
        ) from exc


def _preview_text(event: VorgangEvent | None) -> str | None:
    if event is None:
        return None
    if event.body:
        return event.body[:140]
    return _EVENT_TYPE_PREVIEW.get(event.event_type, event.event_type)


@router.get("", response_model=FeedResponse)
async def get_feed(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    kunde_id: UUID | None = Query(default=None),
    tag: str | None = Query(default=None, description="Tag-Label ohne '#'"),
    leistungstyp: str | None = Query(default=None),
    abrechnungsart: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> FeedResponse:
    stmt = select(Vorgang).order_by(Vorgang.last_activity_at.desc(), Vorgang.id.desc())

    if status_filter:
        stmt = stmt.where(Vorgang.status == status_filter)
    if kunde_id:
        stmt = stmt.where(Vorgang.kunde_id == kunde_id)
    if leistungstyp:
        stmt = stmt.where(Vorgang.leistungstyp == leistungstyp)
    if abrechnungsart:
        stmt = stmt.where(Vorgang.abrechnungsart == abrechnungsart)
    if tag:
        stmt = stmt.where(
            Vorgang.id.in_(
                select(TagAssignment.entity_id)
                .join(Tag, Tag.id == TagAssignment.tag_id)
                .where(TagAssignment.entity_type == "vorgang", Tag.label == tag)
            )
        )
    if cursor:
        last_activity_at, id_ = _decode_cursor(cursor)
        stmt = stmt.where(
            tuple_(Vorgang.last_activity_at, Vorgang.id) < tuple_(last_activity_at, id_)
        )

    stmt = stmt.limit(limit + 1)
    result = await session.execute(stmt)
    vorgaenge = list(result.scalars().all())

    has_more = len(vorgaenge) > limit
    page = vorgaenge[:limit]

    next_cursor = None
    if has_more and page:
        last = page[-1]
        next_cursor = _encode_cursor(last.last_activity_at, last.id)

    items: list[FeedCard] = []
    for vorgang in page:
        kunde = await session.get(Kunde, vorgang.kunde_id)
        anlage_kurzadresse = None
        if vorgang.anlage_id:
            anlage = await session.get(Anlage, vorgang.anlage_id)
            if anlage and anlage.adresse:
                teile = [anlage.adresse.get("strasse"), anlage.adresse.get("ort")]
                anlage_kurzadresse = ", ".join(t for t in teile if t) or None

        last_event_result = await session.execute(
            select(VorgangEvent)
            .where(VorgangEvent.vorgang_id == vorgang.id)
            .order_by(VorgangEvent.id.desc())
            .limit(1)
        )
        last_event = last_event_result.scalar_one_or_none()

        tags_result = await session.execute(
            select(Tag.label)
            .join(TagAssignment, TagAssignment.tag_id == Tag.id)
            .where(TagAssignment.entity_type == "vorgang", TagAssignment.entity_id == vorgang.id)
        )
        tags = [row[0] for row in tags_result.all()]

        timer_result = await session.execute(
            select(Zeiterfassung.id)
            .where(Zeiterfassung.vorgang_id == vorgang.id, Zeiterfassung.ende_at.is_(None))
            .limit(1)
        )
        timer_laeuft = timer_result.scalar_one_or_none() is not None

        items.append(
            FeedCard(
                id=vorgang.id,
                vorgangsnummer=vorgang.vorgangsnummer,
                titel=vorgang.titel,
                kunde_name=kunde.name if kunde else "",
                anlage_kurzadresse=anlage_kurzadresse,
                status=vorgang.status,
                leistungstyp=vorgang.leistungstyp,
                abrechnungsart=vorgang.abrechnungsart,
                prioritaet=vorgang.prioritaet,
                last_activity_at=vorgang.last_activity_at,
                letztes_event_vorschau=_preview_text(last_event),
                tags=tags,
                timer_laeuft=timer_laeuft,
            )
        )

    return FeedResponse(items=items, next_cursor=next_cursor)
