from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.anlage import Anlage
from app.models.kunde import Kunde
from app.models.vertrag import Vertrag
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.vorgang import VorgangCreate, VorgangRead, VorgangUpdate
from app.services.numbering_service import next_vorgangsnummer

router = APIRouter(
    prefix="/api/vorgaenge",
    tags=["vorgaenge"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)


@router.get("", response_model=list[VorgangRead])
async def list_vorgaenge(
    status_filter: str | None = Query(default=None, alias="status"),
    kunde_id: UUID | None = Query(default=None),
    leistungstyp: str | None = Query(default=None),
    abrechnungsart: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
) -> list[Vorgang]:
    stmt = select(Vorgang).order_by(Vorgang.last_activity_at.desc(), Vorgang.id.desc()).limit(limit)
    if status_filter:
        stmt = stmt.where(Vorgang.status == status_filter)
    if kunde_id:
        stmt = stmt.where(Vorgang.kunde_id == kunde_id)
    if leistungstyp:
        stmt = stmt.where(Vorgang.leistungstyp == leistungstyp)
    if abrechnungsart:
        stmt = stmt.where(Vorgang.abrechnungsart == abrechnungsart)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _validate_references(session: AsyncSession, body: VorgangCreate) -> None:
    kunde = await session.get(Kunde, body.kunde_id)
    if kunde is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kunde nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if body.anlage_id is not None:
        anlage = await session.get(Anlage, body.anlage_id)
        if anlage is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Anlage nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
        if anlage.kunde_id != body.kunde_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Anlage gehört nicht zum angegebenen Kunden",
            )
    if body.vertrag_id is not None and await session.get(Vertrag, body.vertrag_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vertrag nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if body.parent_vorgang_id is not None and await session.get(Vorgang, body.parent_vorgang_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Übergeordneter Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )


@router.post("", response_model=VorgangRead, status_code=status.HTTP_201_CREATED)
async def create_vorgang(
    body: VorgangCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Vorgang:
    await _validate_references(session, body)

    vorgangsnummer = body.vorgangsnummer or await next_vorgangsnummer(session, auth.mandant_id)
    vorgang = Vorgang(
        mandant_id=auth.mandant_id,
        vorgangsnummer=vorgangsnummer,
        kunde_id=body.kunde_id,
        anlage_id=body.anlage_id,
        vertrag_id=body.vertrag_id,
        parent_vorgang_id=body.parent_vorgang_id,
        titel=body.titel,
        beschreibung=body.beschreibung,
        abrechnungsart=body.abrechnungsart,
        leistungstyp=body.leistungstyp,
        prioritaet=body.prioritaet,
    )
    session.add(vorgang)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Vorgangsnummer bereits vergeben"
        ) from exc

    session.add(
        VorgangEvent(
            mandant_id=auth.mandant_id,
            vorgang_id=vorgang.id,
            event_type="system",
            author_user_id=auth.user_id,
            is_system=True,
            body="Vorgang angelegt",
            payload={"status": vorgang.status},
        )
    )
    await session.flush()
    await session.refresh(vorgang)
    return vorgang


@router.get("/{vorgang_id}", response_model=VorgangRead)
async def get_vorgang(vorgang_id: UUID, session: AsyncSession = Depends(get_db)) -> Vorgang:
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
    return vorgang


@router.patch("/{vorgang_id}", response_model=VorgangRead)
async def update_vorgang(
    vorgang_id: UUID,
    body: VorgangUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Vorgang:
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")

    changes = body.model_dump(exclude_unset=True)
    alter_status = vorgang.status

    for field, value in changes.items():
        setattr(vorgang, field, value)

    if "status" in changes and changes["status"] != alter_status:
        if changes["status"] == "abgeschlossen" and vorgang.abgeschlossen_am is None:
            vorgang.abgeschlossen_am = datetime.now(timezone.utc)
        session.add(
            VorgangEvent(
                mandant_id=vorgang.mandant_id,
                vorgang_id=vorgang.id,
                event_type="status_change",
                author_user_id=auth.user_id,
                payload={"von": alter_status, "nach": changes["status"]},
            )
        )

    await session.flush()
    if changes:
        await session.refresh(vorgang)
    return vorgang
