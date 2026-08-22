from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AuthContext,
    get_current_user,
    get_db,
    require_recht,
    require_roles,
)
from app.models.kunde import Kunde
from app.models.leistungsverzeichnis import (
    LeistungsverzeichnisPosition,
    LeistungsverzeichnisVerwendung,
)
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.leistungsverzeichnis import (
    LeistungsverzeichnisPositionCreate,
    LeistungsverzeichnisPositionRead,
    LeistungsverzeichnisPositionUpdate,
    LeistungsverzeichnisVerwendungCreate,
    LeistungsverzeichnisVerwendungMitDetails,
    LeistungsverzeichnisVerwendungRead,
)
from app.services import papierkorb_service
from app.services.vorgang_completion_service import VORGANG_STATUS_GESCHLOSSEN

# Gleiche Rollen-/Rechte-Basis wie kunden.py: das Leistungsverzeichnis
# haengt fachlich am Kunden, daher dieselbe "kunden"-Rechtematrix statt
# eines eigenen Rechts.
router = APIRouter(
    prefix="/api/leistungsverzeichnis",
    tags=["leistungsverzeichnis"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("kunden", "sehen")),
    ],
)


async def _require_kunde(session: AsyncSession, kunde_id: UUID) -> Kunde:
    # RLS scopt session.get() bereits auf den eigenen Mandanten.
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None or kunde.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kunde nicht gefunden")
    return kunde


async def _require_position(session: AsyncSession, lv_position_id: UUID) -> LeistungsverzeichnisPosition:
    position = await session.get(LeistungsverzeichnisPosition, lv_position_id)
    if position is None or position.geloescht_am is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Position nicht im Leistungsverzeichnis gefunden"
        )
    return position


@router.get("", response_model=list[LeistungsverzeichnisPositionRead])
async def list_positionen(
    kunde_id: UUID = Query(...),
    nur_stundensaetze: bool = Query(default=False),
    session: AsyncSession = Depends(get_db),
) -> list[LeistungsverzeichnisPosition]:
    stmt = (
        select(LeistungsverzeichnisPosition)
        .where(
            LeistungsverzeichnisPosition.kunde_id == kunde_id,
            LeistungsverzeichnisPosition.geloescht_am.is_(None),
        )
        .order_by(LeistungsverzeichnisPosition.bezeichnung)
    )
    if nur_stundensaetze:
        stmt = stmt.where(LeistungsverzeichnisPosition.ist_stundensatz.is_(True))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/verwendungen", response_model=list[LeistungsverzeichnisVerwendungMitDetails])
async def list_lv_verwendungen(
    vorgang_id: UUID = Query(...),
    session: AsyncSession = Depends(get_db),
) -> list[LeistungsverzeichnisVerwendungMitDetails]:
    stmt = (
        select(
            LeistungsverzeichnisVerwendung,
            LeistungsverzeichnisPosition.bezeichnung,
            LeistungsverzeichnisPosition.einheit,
            LeistungsverzeichnisPosition.einzelpreis,
        )
        .join(LeistungsverzeichnisPosition, LeistungsverzeichnisPosition.id == LeistungsverzeichnisVerwendung.lv_position_id)
        .where(LeistungsverzeichnisVerwendung.vorgang_id == vorgang_id)
        .order_by(LeistungsverzeichnisVerwendung.created_at.desc())
    )
    result = await session.execute(stmt)
    return [
        LeistungsverzeichnisVerwendungMitDetails(
            **LeistungsverzeichnisVerwendungRead.model_validate(verwendung).model_dump(),
            lv_bezeichnung=bezeichnung,
            lv_einheit=einheit,
            lv_einzelpreis=einzelpreis,
        )
        for verwendung, bezeichnung, einheit, einzelpreis in result.all()
    ]


@router.post(
    "",
    response_model=LeistungsverzeichnisPositionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("kunden", "bearbeiten")),
    ],
)
async def create_position(
    body: LeistungsverzeichnisPositionCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> LeistungsverzeichnisPosition:
    await _require_kunde(session, body.kunde_id)
    position = LeistungsverzeichnisPosition(
        mandant_id=auth.mandant_id,
        kunde_id=body.kunde_id,
        bezeichnung=body.bezeichnung,
        einheit=body.einheit,
        einzelpreis=body.einzelpreis,
        ist_stundensatz=body.ist_stundensatz,
        notiz=body.notiz,
    )
    session.add(position)
    await session.flush()
    return position


@router.patch(
    "/{lv_position_id}",
    response_model=LeistungsverzeichnisPositionRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("kunden", "bearbeiten")),
    ],
)
async def update_position(
    lv_position_id: UUID,
    body: LeistungsverzeichnisPositionUpdate,
    session: AsyncSession = Depends(get_db),
) -> LeistungsverzeichnisPosition:
    position = await _require_position(session, lv_position_id)
    changes = body.model_dump(exclude_unset=True)
    for feld, wert in changes.items():
        setattr(position, feld, wert)
    await session.flush()
    return position


@router.delete(
    "/{lv_position_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("kunden", "loeschen")),
    ],
)
async def delete_position(
    lv_position_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    position = await papierkorb_service.soft_delete(
        session, entity_typ="leistungsverzeichnis_position", entity_id=lv_position_id, actor_user_id=auth.user_id
    )
    if position is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position nicht gefunden")


@router.post(
    "/{lv_position_id}/verwendung",
    response_model=LeistungsverzeichnisVerwendungRead,
    status_code=status.HTTP_201_CREATED,
)
async def verwendung_erfassen(
    lv_position_id: UUID,
    body: LeistungsverzeichnisVerwendungCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> LeistungsverzeichnisVerwendung:
    position = await _require_position(session, lv_position_id)
    vorgang = await session.get(Vorgang, body.vorgang_id)
    if vorgang is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if vorgang.kunde_id != position.kunde_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Position gehört nicht zum Kunden dieses Vorgangs",
        )
    if vorgang.status in VORGANG_STATUS_GESCHLOSSEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vorgang ist abgeschlossen und kann nicht mehr bebucht werden",
        )

    verwendung = LeistungsverzeichnisVerwendung(
        mandant_id=auth.mandant_id,
        lv_position_id=lv_position_id,
        vorgang_id=body.vorgang_id,
        menge=body.menge,
        verwendet_von=auth.user_id,
    )
    session.add(verwendung)

    session.add(
        VorgangEvent(
            mandant_id=auth.mandant_id,
            vorgang_id=body.vorgang_id,
            event_type="leistung",
            author_user_id=auth.user_id,
            body=f"{body.menge:g} {position.einheit} {position.bezeichnung} verwendet",
            payload={"lv_position_id": str(lv_position_id), "menge": str(body.menge)},
        )
    )

    await session.flush()
    await session.refresh(verwendung)
    return verwendung
