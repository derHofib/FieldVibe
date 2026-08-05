from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.user import User
from app.schemas.papierkorb import PapierkorbEintragRead
from app.services import papierkorb_service
from app.services.audit_service import log_action

# loesch_ansicht sieht ausschliesslich diesen Router (rein lesend) --
# loesch_operativ hat zusaetzlich ueberall dieselben Rechte wie mandant_admin
# (siehe app/api/deps.py:require_roles()) sowie das Wiederherstellen/
# endgueltige Loeschen unten.
router = APIRouter(
    prefix="/api/papierkorb",
    tags=["papierkorb"],
    dependencies=[Depends(require_roles("loesch_ansicht", "loesch_operativ"))],
)


@router.get("", response_model=list[PapierkorbEintragRead])
async def list_papierkorb(
    entity_typ: str | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[PapierkorbEintragRead]:
    if entity_typ is not None and entity_typ not in papierkorb_service.ENTITY_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unbekannter Entitätstyp"
        )
    if auth.mandant_id is None:
        return []

    eintraege = await papierkorb_service.list_papierkorb(
        session, mandant_id=auth.mandant_id, entity_typ=entity_typ
    )

    namen: dict[UUID, str] = {}
    geloescht_von_ids = {e.geloescht_von for e in eintraege if e.geloescht_von is not None}
    if geloescht_von_ids:
        result = await session.execute(select(User).where(User.id.in_(geloescht_von_ids)))
        namen = {u.id: u.name for u in result.scalars().all()}

    return [
        PapierkorbEintragRead(
            entity_typ=e.entity_typ,
            id=e.id,
            titel=e.titel,
            geloescht_am=e.geloescht_am,
            geloescht_von=e.geloescht_von,
            geloescht_von_name=namen.get(e.geloescht_von) if e.geloescht_von else None,
        )
        for e in eintraege
    ]


@router.post(
    "/{entity_typ}/{entity_id}/wiederherstellen",
    dependencies=[Depends(require_roles("loesch_operativ"))],
    status_code=status.HTTP_204_NO_CONTENT,
)
async def wiederherstellen(
    entity_typ: str,
    entity_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    if entity_typ not in papierkorb_service.ENTITY_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unbekannter Entitätstyp"
        )
    obj = await papierkorb_service.restore(session, entity_typ=entity_typ, entity_id=entity_id)
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Datensatz nicht im Papierkorb gefunden",
        )
    await log_action(
        session,
        aktion="papierkorb_wiederhergestellt",
        mandant_id=auth.mandant_id,
        actor_user_id=auth.user_id,
        entity_type=entity_typ,
        entity_id=entity_id,
    )


@router.delete(
    "/{entity_typ}/{entity_id}",
    dependencies=[Depends(require_roles("loesch_operativ"))],
    status_code=status.HTTP_204_NO_CONTENT,
)
async def endgueltig_loeschen(
    entity_typ: str,
    entity_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    if entity_typ not in papierkorb_service.ENTITY_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unbekannter Entitätstyp"
        )
    try:
        geloescht = await papierkorb_service.purge(
            session, entity_typ=entity_typ, entity_id=entity_id
        )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Datensatz kann nicht endgültig gelöscht werden, da noch andere Daten "
                "darauf verweisen."
            ),
        ) from exc
    if not geloescht:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Datensatz nicht im Papierkorb gefunden",
        )
    await log_action(
        session,
        aktion="papierkorb_endgueltig_geloescht",
        mandant_id=auth.mandant_id,
        actor_user_id=auth.user_id,
        entity_type=entity_typ,
        entity_id=entity_id,
    )
