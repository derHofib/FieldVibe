from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.anlage import Anlage
from app.models.dauerauftrag import Dauerauftrag
from app.models.kunde import Kunde
from app.models.vorgang import Vorgang
from app.schemas.dauerauftrag import (
    DauerauftragCreate,
    DauerauftragMitVerlauf,
    DauerauftragRead,
    DauerauftragUpdate,
)
from app.services.zuweisung_service import assigned_kunde_ids

router = APIRouter(
    prefix="/api/dauerauftraege",
    tags=["dauerauftraege"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)


@router.get("", response_model=list[DauerauftragRead])
async def list_dauerauftraege(
    kunde_id: UUID | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Dauerauftrag]:
    stmt = select(Dauerauftrag).order_by(Dauerauftrag.naechste_faelligkeit_am.asc())
    if kunde_id:
        stmt = stmt.where(Dauerauftrag.kunde_id == kunde_id)
    if auth.role == "techniker":
        stmt = stmt.where(Dauerauftrag.kunde_id.in_(await assigned_kunde_ids(session, auth.user_id)))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "",
    response_model=DauerauftragRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_dauerauftrag(
    body: DauerauftragCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Dauerauftrag:
    if await session.get(Kunde, body.kunde_id) is None:
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

    dauerauftrag = Dauerauftrag(
        mandant_id=auth.mandant_id,
        kunde_id=body.kunde_id,
        anlage_id=body.anlage_id,
        titel=body.titel,
        beschreibung=body.beschreibung,
        abrechnungsart=body.abrechnungsart,
        leistungstyp=body.leistungstyp,
        intervall_tage=body.intervall_tage,
        naechste_faelligkeit_am=body.naechste_faelligkeit_am,
        modus=body.modus,
        toleranz_frueh_tage=body.toleranz_frueh_tage,
        toleranz_spaet_tage=body.toleranz_spaet_tage,
    )
    session.add(dauerauftrag)
    await session.flush()
    await session.refresh(dauerauftrag)
    return dauerauftrag


async def _require_dauerauftrag_zugriff(
    session: AsyncSession, auth: AuthContext, dauerauftrag: Dauerauftrag
) -> None:
    if auth.role == "techniker" and dauerauftrag.kunde_id not in await assigned_kunde_ids(
        session, auth.user_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dauerauftrag nicht gefunden"
        )


@router.get("/{dauerauftrag_id}", response_model=DauerauftragMitVerlauf)
async def get_dauerauftrag(
    dauerauftrag_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DauerauftragMitVerlauf:
    dauerauftrag = await session.get(Dauerauftrag, dauerauftrag_id)
    if dauerauftrag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dauerauftrag nicht gefunden"
        )
    await _require_dauerauftrag_zugriff(session, auth, dauerauftrag)

    vorgaenge_result = await session.execute(
        select(Vorgang)
        .where(Vorgang.dauerauftrag_id == dauerauftrag_id)
        .order_by(Vorgang.created_at.desc())
    )
    return DauerauftragMitVerlauf(
        **DauerauftragRead.model_validate(dauerauftrag).model_dump(),
        vorgaenge=list(vorgaenge_result.scalars().all()),
    )


@router.patch(
    "/{dauerauftrag_id}",
    response_model=DauerauftragRead,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def update_dauerauftrag(
    dauerauftrag_id: UUID,
    body: DauerauftragUpdate,
    session: AsyncSession = Depends(get_db),
) -> Dauerauftrag:
    dauerauftrag = await session.get(Dauerauftrag, dauerauftrag_id)
    if dauerauftrag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dauerauftrag nicht gefunden"
        )

    if body.anlage_id is not None:
        anlage = await session.get(Anlage, body.anlage_id)
        if anlage is None or anlage.kunde_id != dauerauftrag.kunde_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Anlage nicht gefunden oder gehört nicht zum Kunden dieses Dauerauftrags",
            )

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(dauerauftrag, field, value)
    await session.flush()
    if changes:
        await session.refresh(dauerauftrag)
    return dauerauftrag


@router.delete(
    "/{dauerauftrag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def delete_dauerauftrag(
    dauerauftrag_id: UUID, session: AsyncSession = Depends(get_db)
) -> None:
    # Bereits erzeugte Vorgaenge bleiben unangetastet -- sie verlieren nur
    # ihre dauerauftrag_id (ON DELETE SET NULL, siehe Migration 0013), sind
    # aber ganz normale Vorgaenge und werden nicht geloescht.
    dauerauftrag = await session.get(Dauerauftrag, dauerauftrag_id)
    if dauerauftrag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dauerauftrag nicht gefunden"
        )
    await session.delete(dauerauftrag)
    await session.flush()
