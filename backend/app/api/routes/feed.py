import base64
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.anlage import Anlage
from app.models.kunde import Kunde
from app.models.kundenportal import KundenportalZugang
from app.models.standort import Standort
from app.models.tag import Tag, TagAssignment
from app.models.user import User
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.models.zeiterfassung import Zeiterfassung
from app.schemas.feed import FeedCard, FeedResponse
from app.services.rechte_service import ist_auf_zugewiesene_kunden_beschraenkt
from app.services.zuweisung_service import assigned_kunde_ids

router = APIRouter(
    prefix="/api/feed",
    tags=["feed"],
    dependencies=[Depends(require_roles("mandant_admin", "custom", "loesch_operativ"))],
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


def _encode_cursor(last_activity_at, prioritaet: int, id_: UUID) -> str:
    # Fuehrt immer last_activity_at UND prioritaet mit, unabhaengig vom
    # aktiven sort-Modus -- so bleibt die Cursor-Form fuer beide
    # Sortierungen gleich, statt zwei verschiedene Formate pflegen zu
    # muessen (siehe get_feed: welches Feld davon der Vergleich tatsaechlich
    # nutzt, haengt nur vom `sort`-Parameter ab).
    raw = f"{last_activity_at.isoformat()}|{prioritaet}|{id_}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, int, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        last_activity_at, prioritaet, id_ = raw.split("|", 2)
        return datetime.fromisoformat(last_activity_at), int(prioritaet), UUID(id_)
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
    sort: str = Query(default="last_activity_at", pattern="^(last_activity_at|prioritaet)$"),
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="Ein oder mehrere Status, kommagetrennt (z.B. 'neu,in_arbeit')",
    ),
    kunde_id: UUID | None = Query(default=None),
    anlage_id: UUID | None = Query(default=None),
    standort_id: UUID | None = Query(default=None),
    tag: str | None = Query(default=None, description="Tag-Label ohne '#'"),
    leistungstyp: str | None = Query(default=None),
    abrechnungsart: str | None = Query(default=None),
    faellig_von: date | None = Query(default=None),
    faellig_bis: date | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> FeedResponse:
    stmt = select(Vorgang).where(Vorgang.geloescht_am.is_(None))
    if sort == "prioritaet":
        stmt = stmt.order_by(
            Vorgang.prioritaet.desc(), Vorgang.last_activity_at.desc(), Vorgang.id.desc()
        )
    else:
        stmt = stmt.order_by(Vorgang.last_activity_at.desc(), Vorgang.id.desc())

    if status_filter:
        status_liste = [s for s in status_filter.split(",") if s]
        if status_liste:
            stmt = stmt.where(Vorgang.status.in_(status_liste))
    if kunde_id:
        stmt = stmt.where(Vorgang.kunde_id == kunde_id)
    if anlage_id:
        stmt = stmt.where(Vorgang.anlage_id == anlage_id)
    if standort_id:
        stmt = stmt.where(Vorgang.standort_id == standort_id)
    if leistungstyp:
        stmt = stmt.where(Vorgang.leistungstyp == leistungstyp)
    if abrechnungsart:
        stmt = stmt.where(Vorgang.abrechnungsart == abrechnungsart)
    if faellig_von:
        stmt = stmt.where(
            Vorgang.faelligkeit_am >= datetime.combine(faellig_von, datetime.min.time(), tzinfo=timezone.utc)
        )
    if faellig_bis:
        stmt = stmt.where(
            Vorgang.faelligkeit_am
            < datetime.combine(faellig_bis + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        )
    if await ist_auf_zugewiesene_kunden_beschraenkt(
        session, role=auth.role, account_typ_id=auth.account_typ_id
    ):
        stmt = stmt.where(Vorgang.kunde_id.in_(await assigned_kunde_ids(session, auth.user_id)))
    if tag:
        stmt = stmt.where(
            Vorgang.id.in_(
                select(TagAssignment.entity_id)
                .join(Tag, Tag.id == TagAssignment.tag_id)
                .where(TagAssignment.entity_type == "vorgang", Tag.label == tag)
            )
        )
    if cursor:
        last_activity_at, prioritaet, id_ = _decode_cursor(cursor)
        if sort == "prioritaet":
            stmt = stmt.where(
                tuple_(Vorgang.prioritaet, Vorgang.last_activity_at, Vorgang.id)
                < tuple_(prioritaet, last_activity_at, id_)
            )
        else:
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
        next_cursor = _encode_cursor(last.last_activity_at, last.prioritaet, last.id)

    vorgang_ids = [v.id for v in page]

    kunde_ids = {v.kunde_id for v in page}
    kunden_by_id: dict[UUID, Kunde] = {}
    if kunde_ids:
        kunden_result = await session.execute(select(Kunde).where(Kunde.id.in_(kunde_ids)))
        kunden_by_id = {k.id: k for k in kunden_result.scalars().all()}

    anlage_ids = {v.anlage_id for v in page if v.anlage_id}
    anlagen_by_id: dict[UUID, Anlage] = {}
    if anlage_ids:
        anlagen_result = await session.execute(select(Anlage).where(Anlage.id.in_(anlage_ids)))
        anlagen_by_id = {a.id: a for a in anlagen_result.scalars().all()}

    standort_ids = {v.standort_id for v in page if v.standort_id}
    standorte_by_id: dict[UUID, Standort] = {}
    if standort_ids:
        standorte_result = await session.execute(select(Standort).where(Standort.id.in_(standort_ids)))
        standorte_by_id = {s.id: s for s in standorte_result.scalars().all()}

    # Eine gemeinsame Query fuer Ersteller UND zugewiesenen Mitarbeiter --
    # beide sind User-IDs, eine zweite Roundtrip nur fuer zugewiesener_name
    # waere unnoetig.
    ersteller_ids = {v.erstellt_von for v in page if v.erstellt_von} | {
        v.zugewiesener_user_id for v in page if v.zugewiesener_user_id
    }
    ersteller_by_id: dict[UUID, User] = {}
    if ersteller_ids:
        ersteller_result = await session.execute(select(User).where(User.id.in_(ersteller_ids)))
        ersteller_by_id = {u.id: u for u in ersteller_result.scalars().all()}

    portal_ersteller_ids = {
        v.erstellt_von_kundenportal_zugang_id for v in page if v.erstellt_von_kundenportal_zugang_id
    }
    portal_ersteller_by_id: dict[UUID, KundenportalZugang] = {}
    if portal_ersteller_ids:
        portal_ersteller_result = await session.execute(
            select(KundenportalZugang).where(KundenportalZugang.id.in_(portal_ersteller_ids))
        )
        portal_ersteller_by_id = {z.id: z for z in portal_ersteller_result.scalars().all()}

    last_events_by_vorgang: dict[UUID, VorgangEvent] = {}
    if vorgang_ids:
        # DISTINCT ON (Postgres) statt einer eigenen Query pro Vorgang: eine
        # Row pro vorgang_id, die mit der groessten id (= neuestes Event)
        # dank passender order_by-Reihenfolge.
        last_event_result = await session.execute(
            select(VorgangEvent)
            .where(VorgangEvent.vorgang_id.in_(vorgang_ids))
            .order_by(VorgangEvent.vorgang_id, VorgangEvent.id.desc())
            .distinct(VorgangEvent.vorgang_id)
        )
        last_events_by_vorgang = {e.vorgang_id: e for e in last_event_result.scalars().all()}

    tags_by_vorgang: dict[UUID, list[str]] = defaultdict(list)
    if vorgang_ids:
        tags_result = await session.execute(
            select(TagAssignment.entity_id, Tag.label)
            .join(Tag, Tag.id == TagAssignment.tag_id)
            .where(
                TagAssignment.entity_type == "vorgang", TagAssignment.entity_id.in_(vorgang_ids)
            )
        )
        for entity_id, label in tags_result.all():
            tags_by_vorgang[entity_id].append(label)

    vorgaenge_mit_laufendem_timer: set[UUID] = set()
    if vorgang_ids:
        timer_result = await session.execute(
            select(Zeiterfassung.vorgang_id).where(
                Zeiterfassung.vorgang_id.in_(vorgang_ids), Zeiterfassung.ende_at.is_(None)
            )
        )
        vorgaenge_mit_laufendem_timer = {row[0] for row in timer_result.all()}

    items: list[FeedCard] = []
    for vorgang in page:
        kunde = kunden_by_id.get(vorgang.kunde_id)
        anlage = anlagen_by_id.get(vorgang.anlage_id) if vorgang.anlage_id else None
        anlage_kurzadresse = None
        if anlage and anlage.adresse:
            teile = [anlage.adresse.get("strasse"), anlage.adresse.get("ort")]
            anlage_kurzadresse = ", ".join(t for t in teile if t) or None
        standort = standorte_by_id.get(vorgang.standort_id) if vorgang.standort_id else None

        # Koordinaten nur vertrauen, wenn die tatsaechlich angezeigte Adresse
        # von Standort/Anlage kommt -- ein manueller Adress-Override am
        # Vorgang selbst hat keine eigenen geo_lat/geo_lng-Spalten (siehe
        # gleiche Regel in VorgangDetailPage.tsx/MapboxMap, Phase 2).
        # Standort ist die spezifischere "Ausfuehrungsadresse" und hat daher
        # Vorrang vor der Anlage.
        geo_lat = geo_lng = None
        if not vorgang.adresse:
            if standort and standort.geo_lat is not None and standort.geo_lng is not None:
                geo_lat, geo_lng = standort.geo_lat, standort.geo_lng
            elif anlage and anlage.geo_lat is not None and anlage.geo_lng is not None:
                geo_lat, geo_lng = anlage.geo_lat, anlage.geo_lng

        ersteller_name = None
        if vorgang.erstellt_von:
            ersteller = ersteller_by_id.get(vorgang.erstellt_von)
            ersteller_name = ersteller.name if ersteller else None
        elif vorgang.erstellt_von_kundenportal_zugang_id:
            portal_ersteller = portal_ersteller_by_id.get(vorgang.erstellt_von_kundenportal_zugang_id)
            ersteller_name = f"{portal_ersteller.name} (Kunde)" if portal_ersteller else None

        zugewiesener_name = None
        if vorgang.zugewiesener_user_id:
            zugewiesener = ersteller_by_id.get(vorgang.zugewiesener_user_id)
            zugewiesener_name = zugewiesener.name if zugewiesener else None

        items.append(
            FeedCard(
                id=vorgang.id,
                vorgangsnummer=vorgang.vorgangsnummer,
                titel=vorgang.titel,
                kunde_name=kunde.name if kunde else "",
                anlage_kurzadresse=anlage_kurzadresse,
                anlage_bezeichnung=anlage.bezeichnung if anlage else None,
                standort_bezeichnung=standort.bezeichnung if standort else None,
                ersteller_name=ersteller_name,
                status=vorgang.status,
                leistungstyp=vorgang.leistungstyp,
                abrechnungsart=vorgang.abrechnungsart,
                prioritaet=vorgang.prioritaet,
                faelligkeit_am=vorgang.faelligkeit_am,
                last_activity_at=vorgang.last_activity_at,
                letztes_event_vorschau=_preview_text(last_events_by_vorgang.get(vorgang.id)),
                tags=tags_by_vorgang.get(vorgang.id, []),
                geo_lat=geo_lat,
                geo_lng=geo_lng,
                timer_laeuft=vorgang.id in vorgaenge_mit_laufendem_timer,
                dauerauftrag_id=vorgang.dauerauftrag_id,
                zugewiesener_name=zugewiesener_name,
            )
        )

    return FeedResponse(items=items, next_cursor=next_cursor)
