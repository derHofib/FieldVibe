from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_recht, require_roles
from app.models.auftrag import Auftrag
from app.models.kunde import Kunde
from app.models.projekt import Projekt
from app.models.vorgang import Vorgang
from app.schemas.auftrag import AuftragCreate, AuftragRead, AuftragUpdate
from app.services import papierkorb_service

# Nutzt bewusst den bestehenden Rechte-Bereich "projekte" (siehe
# app/models/auftrag.py) -- kein eigener Bereich noetig.
router = APIRouter(
    prefix="/api/auftraege",
    tags=["auftraege"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("projekte", "sehen")),
    ],
)


async def _require_auftrag(session: AsyncSession, auftrag_id: UUID) -> Auftrag:
    auftrag = await session.get(Auftrag, auftrag_id)
    if auftrag is None or auftrag.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auftrag nicht gefunden")
    return auftrag


async def _anreichern(session: AsyncSession, auftraege: list[Auftrag]) -> list[AuftragRead]:
    """Kunde-Name + Vorgaenge-Anzahl transient anreichern (gleiches Muster
    wie VorgangRead.zugewiesener_name) -- erspart dem Frontend zusaetzliche
    Abfragen fuer die Tabellen-Ansicht."""
    if not auftraege:
        return []
    kunde_ids = {a.kunde_id for a in auftraege if a.kunde_id is not None}
    kunden_namen: dict[UUID, str] = {}
    if kunde_ids:
        result = await session.execute(select(Kunde.id, Kunde.name).where(Kunde.id.in_(kunde_ids)))
        kunden_namen = {row.id: row.name for row in result}

    vorgaenge_counts: dict[UUID, int] = {}
    auftrag_ids = [a.id for a in auftraege]
    count_result = await session.execute(
        select(Vorgang.auftrag_id, func.count(Vorgang.id))
        .where(Vorgang.auftrag_id.in_(auftrag_ids), Vorgang.geloescht_am.is_(None))
        .group_by(Vorgang.auftrag_id)
    )
    vorgaenge_counts = {row[0]: row[1] for row in count_result}

    gelesen = []
    for auftrag in auftraege:
        read = AuftragRead.model_validate(auftrag)
        if auftrag.kunde_id is not None:
            read.kunde_name = kunden_namen.get(auftrag.kunde_id)
        read.vorgaenge_gesamt = vorgaenge_counts.get(auftrag.id, 0)
        gelesen.append(read)
    return gelesen


@router.get("", response_model=list[AuftragRead])
async def list_auftraege(
    projekt_id: UUID | None = Query(default=None),
    kunde_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_db),
) -> list[AuftragRead]:
    stmt = select(Auftrag).where(Auftrag.geloescht_am.is_(None)).order_by(Auftrag.created_at.desc())
    if projekt_id:
        stmt = stmt.where(Auftrag.projekt_id == projekt_id)
    if kunde_id:
        stmt = stmt.where(Auftrag.kunde_id == kunde_id)
    if status_filter:
        stmt = stmt.where(Auftrag.status == status_filter)
    result = await session.execute(stmt)
    return await _anreichern(session, list(result.scalars().all()))


@router.post(
    "",
    response_model=AuftragRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_recht("projekte", "erstellen"))],
)
async def create_auftrag(
    body: AuftragCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AuftragRead:
    if body.projekt_id is not None and await session.get(Projekt, body.projekt_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Projekt nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if body.kunde_id is not None and await session.get(Kunde, body.kunde_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kunde nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    auftrag = Auftrag(
        mandant_id=auth.mandant_id,
        projekt_id=body.projekt_id,
        kunde_id=body.kunde_id,
        titel=body.titel,
        beschreibung=body.beschreibung,
        erstellt_von=auth.user_id,
    )
    session.add(auftrag)
    await session.flush()
    await session.refresh(auftrag)
    [gelesen] = await _anreichern(session, [auftrag])
    return gelesen


@router.get("/{auftrag_id}", response_model=AuftragRead)
async def get_auftrag(auftrag_id: UUID, session: AsyncSession = Depends(get_db)) -> AuftragRead:
    auftrag = await _require_auftrag(session, auftrag_id)
    [gelesen] = await _anreichern(session, [auftrag])
    return gelesen


@router.patch(
    "/{auftrag_id}",
    response_model=AuftragRead,
    dependencies=[Depends(require_recht("projekte", "bearbeiten"))],
)
async def update_auftrag(
    auftrag_id: UUID,
    body: AuftragUpdate,
    session: AsyncSession = Depends(get_db),
) -> AuftragRead:
    auftrag = await _require_auftrag(session, auftrag_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("projekt_id") is not None and await session.get(Projekt, changes["projekt_id"]) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Projekt nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if changes.get("kunde_id") is not None and await session.get(Kunde, changes["kunde_id"]) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kunde nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    for feld, wert in changes.items():
        setattr(auftrag, feld, wert)
    await session.flush()
    await session.refresh(auftrag)
    [gelesen] = await _anreichern(session, [auftrag])
    return gelesen


@router.delete(
    "/{auftrag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_recht("projekte", "loeschen"))],
)
async def delete_auftrag(
    auftrag_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    auftrag = await papierkorb_service.soft_delete(
        session, entity_typ="auftrag", entity_id=auftrag_id, actor_user_id=auth.user_id
    )
    if auftrag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auftrag nicht gefunden")
