from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.models.zeiterfassung import Zeiterfassung
from app.schemas.zeiterfassung import ZeiterfassungRead, ZeiterfassungStart
from app.services.event_bus import event_bus
from app.services.zuweisung_service import assigned_kunde_ids

router = APIRouter(
    prefix="/api/zeiterfassung",
    tags=["zeiterfassung"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)


@router.get("", response_model=list[ZeiterfassungRead])
async def list_zeiterfassung(
    vorgang_id: UUID | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Zeiterfassung]:
    stmt = select(Zeiterfassung).order_by(Zeiterfassung.start_at.desc())
    if vorgang_id:
        stmt = stmt.where(Zeiterfassung.vorgang_id == vorgang_id)
    if auth.role == "techniker":
        stmt = stmt.where(
            Zeiterfassung.vorgang_id.in_(
                select(Vorgang.id).where(
                    Vorgang.kunde_id.in_(await assigned_kunde_ids(session, auth.user_id))
                )
            )
        )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/laufend", response_model=ZeiterfassungRead | None)
async def get_laufender_timer(
    auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> Zeiterfassung | None:
    result = await session.execute(
        select(Zeiterfassung).where(
            Zeiterfassung.techniker_id == auth.user_id, Zeiterfassung.ende_at.is_(None)
        )
    )
    return result.scalar_one_or_none()


@router.post("/start", response_model=ZeiterfassungRead, status_code=status.HTTP_201_CREATED)
async def start_timer(
    body: ZeiterfassungStart,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Zeiterfassung:
    vorgang = await session.get(Vorgang, body.vorgang_id)
    if vorgang is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if auth.role == "techniker" and vorgang.kunde_id not in await assigned_kunde_ids(
        session, auth.user_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Dieser Kunde ist dir nicht zugewiesen"
        )

    eintrag = Zeiterfassung(
        mandant_id=auth.mandant_id,
        vorgang_id=body.vorgang_id,
        techniker_id=auth.user_id,
        start_at=datetime.now(timezone.utc),
        taetigkeit=body.taetigkeit,
        abrechenbar=body.abrechenbar,
    )
    session.add(eintrag)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Es läuft bereits ein Timer für diesen Techniker",
        ) from exc

    session.add(
        VorgangEvent(
            mandant_id=auth.mandant_id,
            vorgang_id=body.vorgang_id,
            event_type="zeit_start",
            author_user_id=auth.user_id,
            payload={"zeiterfassung_id": str(eintrag.id), "taetigkeit": body.taetigkeit},
        )
    )
    await session.flush()

    await event_bus.publish(
        auth.mandant_id,
        "timer",
        {"vorgang_id": str(body.vorgang_id), "techniker_id": str(auth.user_id), "laeuft": True},
    )
    return eintrag


@router.post("/{zeiterfassung_id}/stop", response_model=ZeiterfassungRead)
async def stop_timer(
    zeiterfassung_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Zeiterfassung:
    eintrag = await session.get(Zeiterfassung, zeiterfassung_id)
    if eintrag is None or eintrag.techniker_id != auth.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Zeiterfassung nicht gefunden"
        )
    if eintrag.ende_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Timer läuft nicht mehr"
        )

    eintrag.ende_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(eintrag)

    session.add(
        VorgangEvent(
            mandant_id=auth.mandant_id,
            vorgang_id=eintrag.vorgang_id,
            event_type="zeit_stop",
            author_user_id=auth.user_id,
            payload={
                "zeiterfassung_id": str(eintrag.id),
                "dauer_sekunden": int((eintrag.ende_at - eintrag.start_at).total_seconds()),
            },
        )
    )
    await session.flush()

    await event_bus.publish(
        auth.mandant_id,
        "timer",
        {"vorgang_id": str(eintrag.vorgang_id), "techniker_id": str(auth.user_id), "laeuft": False},
    )
    return eintrag
