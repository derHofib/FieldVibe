from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AuthContext,
    get_current_user,
    get_db,
    require_module,
    require_recht,
    require_roles,
)
from app.models.termin import Termin
from app.models.user import User
from app.models.vorgang import Vorgang
from app.schemas.termin import TerminCreate, TerminCreateResult, TerminRead, TerminUpdate
from app.services import papierkorb_service
from app.services.dispo_service import compute_warnungen
from app.services.event_bus import event_bus

router = APIRouter(
    prefix="/api/termine",
    tags=["termine"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_module("dispo")),
        Depends(require_recht("dispo", "sehen")),
    ],
)


async def _load_vorgang_and_techniker(
    session: AsyncSession, vorgang_id: UUID, techniker_id: UUID
) -> Vorgang:
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    techniker = await session.get(User, techniker_id)
    if (
        techniker is None
        or techniker.mandant_id != vorgang.mandant_id
        or techniker.role not in ("mandant_admin", "custom")
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Techniker nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    return vorgang


@router.get("", response_model=list[TerminRead])
async def list_termine(
    techniker_id: UUID | None = Query(default=None),
    vorgang_id: UUID | None = Query(default=None),
    von: datetime | None = Query(default=None),
    bis: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> list[Termin]:
    stmt = select(Termin).where(Termin.geloescht_am.is_(None)).order_by(Termin.start_at.asc())
    if techniker_id:
        stmt = stmt.where(Termin.techniker_id == techniker_id)
    if vorgang_id:
        stmt = stmt.where(Termin.vorgang_id == vorgang_id)
    if von:
        stmt = stmt.where(Termin.ende_at >= von)
    if bis:
        stmt = stmt.where(Termin.start_at <= bis)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/{termin_id}", response_model=TerminRead)
async def get_termin(termin_id: UUID, session: AsyncSession = Depends(get_db)) -> Termin:
    termin = await session.get(Termin, termin_id)
    if termin is None or termin.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Termin nicht gefunden")
    return termin


@router.post(
    "",
    response_model=TerminCreateResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("dispo", "erstellen")),
    ],
)
async def create_termin(
    body: TerminCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> TerminCreateResult:
    vorgang = await _load_vorgang_and_techniker(session, body.vorgang_id, body.techniker_id)

    warnungen = await compute_warnungen(
        session,
        techniker_id=body.techniker_id,
        start_at=body.start_at,
        ende_at=body.ende_at,
        anlage_id=vorgang.anlage_id,
    )

    termin = Termin(
        mandant_id=auth.mandant_id,
        vorgang_id=body.vorgang_id,
        techniker_id=body.techniker_id,
        erstellt_von=auth.user_id,
        titel=body.titel,
        start_at=body.start_at,
        ende_at=body.ende_at,
        notiz=body.notiz,
    )
    session.add(termin)
    await session.flush()
    await session.refresh(termin)

    await event_bus.publish(
        auth.mandant_id,
        "termin_update",
        {"termin_id": str(termin.id), "techniker_id": str(termin.techniker_id), "reason": "erstellt"},
    )
    return TerminCreateResult(termin=TerminRead.model_validate(termin), warnungen=warnungen)


@router.patch(
    "/{termin_id}",
    response_model=TerminCreateResult,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("dispo", "bearbeiten")),
    ],
)
async def update_termin(
    termin_id: UUID,
    body: TerminUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> TerminCreateResult:
    termin = await session.get(Termin, termin_id)
    if termin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Termin nicht gefunden")

    changes = body.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] not in (
        "geplant",
        "bestaetigt",
        "abgeschlossen",
        "abgesagt",
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ungültiger Status")

    new_techniker_id = changes.get("techniker_id", termin.techniker_id)
    new_start_at = changes.get("start_at", termin.start_at)
    new_ende_at = changes.get("ende_at", termin.ende_at)
    if new_ende_at <= new_start_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="ende_at muss nach start_at liegen"
        )

    vorgang = await session.get(Vorgang, termin.vorgang_id)
    if "techniker_id" in changes:
        await _load_vorgang_and_techniker(session, termin.vorgang_id, new_techniker_id)

    warnungen = []
    if changes.get("status", termin.status) != "abgesagt":
        warnungen = await compute_warnungen(
            session,
            techniker_id=new_techniker_id,
            start_at=new_start_at,
            ende_at=new_ende_at,
            anlage_id=vorgang.anlage_id if vorgang else None,
            exclude_termin_id=termin.id,
        )

    for field, value in changes.items():
        setattr(termin, field, value)

    await session.flush()
    await session.refresh(termin)

    await event_bus.publish(
        auth.mandant_id,
        "termin_update",
        {"termin_id": str(termin.id), "techniker_id": str(termin.techniker_id), "reason": "geaendert"},
    )
    return TerminCreateResult(termin=TerminRead.model_validate(termin), warnungen=warnungen)


@router.delete(
    "/{termin_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("dispo", "loeschen")),
    ],
)
async def delete_termin(
    termin_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    termin = await papierkorb_service.soft_delete(
        session, entity_typ="termin", entity_id=termin_id, actor_user_id=auth.user_id
    )
    if termin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Termin nicht gefunden")
