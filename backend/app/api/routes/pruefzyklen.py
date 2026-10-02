from datetime import datetime, time, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AuthContext,
    get_current_user,
    get_db,
    require_module,
    require_recht,
    require_roles,
)
from app.models.anlage import Anlage
from app.models.pruefzyklus import Pruefzyklus
from app.schemas.pruefzyklus import PruefzyklusCreate, PruefzyklusRead, PruefzyklusUpdate
from app.services import papierkorb_service
from app.services.date_utils import add_intervall
from app.services.zuweisung_service import erlaubte_kunde_ids, require_kunde_zugewiesen

# loesch_operativ hat ueberall dieselben Rechte wie mandant_admin (siehe
# app/api/deps.py:require_roles()) und braucht daher wie dieser Zugriff auf
# diesen Router.
router = APIRouter(
    prefix="/api/pruefzyklen",
    tags=["pruefzyklen"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_module("pruefzyklen")),
    ],
)


@router.get(
    "", response_model=list[PruefzyklusRead], dependencies=[Depends(require_recht("material", "sehen"))]
)
async def list_pruefzyklen(
    anlage_id: UUID | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Pruefzyklus]:
    stmt = (
        select(Pruefzyklus)
        .where(Pruefzyklus.geloescht_am.is_(None))
        .order_by(Pruefzyklus.naechste_pruefung_am.asc())
    )
    if anlage_id:
        stmt = stmt.where(Pruefzyklus.anlage_id == anlage_id)
    erlaubte_kunden = await erlaubte_kunde_ids(session, auth)
    if erlaubte_kunden is not None:
        stmt = stmt.where(
            Pruefzyklus.anlage_id.in_(
                select(Anlage.id).where(or_(Anlage.kunde_id.is_(None), Anlage.kunde_id.in_(erlaubte_kunden)))
            )
        )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _require_pruefzyklus_zugriff(
    session: AsyncSession, auth: AuthContext, anlage_id: UUID
) -> None:
    """Pruefzyklen an Anlagen ohne Kunde (Fahrzeuge/Pruefmittel) bleiben fuer
    Eingeschraenkte sichtbar; Kundenanlagen nur bei zugewiesenem Kunden (404)."""
    erlaubt = await erlaubte_kunde_ids(session, auth)
    if erlaubt is None:
        return
    anlage = await session.get(Anlage, anlage_id)
    if anlage is not None and anlage.kunde_id is not None and anlage.kunde_id not in erlaubt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prüfzyklus nicht gefunden")


@router.post(
    "",
    response_model=PruefzyklusRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("material", "erstellen")),
    ],
)
async def create_pruefzyklus(
    body: PruefzyklusCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Pruefzyklus:
    anlage = await session.get(Anlage, body.anlage_id)
    if anlage is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anlage nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if anlage.kunde_id is not None:
        await require_kunde_zugewiesen(session, auth, anlage.kunde_id)

    basis = (
        datetime.combine(body.letzte_pruefung_am, time.min, tzinfo=timezone.utc)
        if body.letzte_pruefung_am
        else datetime.now(timezone.utc)
    )
    pruefzyklus = Pruefzyklus(
        mandant_id=auth.mandant_id,
        anlage_id=body.anlage_id,
        bezeichnung=body.bezeichnung,
        intervall_wert=body.intervall_wert,
        intervall_einheit=body.intervall_einheit,
        letzte_pruefung_am=basis if body.letzte_pruefung_am else None,
        naechste_pruefung_am=add_intervall(basis, body.intervall_einheit, body.intervall_wert),
    )
    session.add(pruefzyklus)
    await session.flush()
    await session.refresh(pruefzyklus)
    return pruefzyklus


@router.get(
    "/{pruefzyklus_id}",
    response_model=PruefzyklusRead,
    dependencies=[Depends(require_recht("material", "sehen"))],
)
async def get_pruefzyklus(
    pruefzyklus_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Pruefzyklus:
    pruefzyklus = await session.get(Pruefzyklus, pruefzyklus_id)
    if pruefzyklus is None or pruefzyklus.geloescht_am is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prüfzyklus nicht gefunden"
        )
    await _require_pruefzyklus_zugriff(session, auth, pruefzyklus.anlage_id)
    return pruefzyklus


@router.patch(
    "/{pruefzyklus_id}",
    response_model=PruefzyklusRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("material", "bearbeiten")),
    ],
)
async def update_pruefzyklus(
    pruefzyklus_id: UUID,
    body: PruefzyklusUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Pruefzyklus:
    pruefzyklus = await session.get(Pruefzyklus, pruefzyklus_id)
    if pruefzyklus is None or pruefzyklus.geloescht_am is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prüfzyklus nicht gefunden"
        )

    await _require_pruefzyklus_zugriff(session, auth, pruefzyklus.anlage_id)

    changes = body.model_dump(exclude_unset=True)
    letzte_pruefung_explizit_gesetzt = "letzte_pruefung_am" in changes
    naechste_pruefung_explizit_gesetzt = "naechste_pruefung_am" in changes
    if changes.get("letzte_pruefung_am") is not None:
        changes["letzte_pruefung_am"] = datetime.combine(
            changes["letzte_pruefung_am"], time.min, tzinfo=timezone.utc
        )

    for field, value in changes.items():
        setattr(pruefzyklus, field, value)

    # Wird eine durchgefuehrte Pruefung eingetragen (oder das Intervall
    # geaendert), ohne dass die naechste Faelligkeit explizit mitgegeben
    # wurde, automatisch neu berechnen -- sonst muesste das Frontend diese
    # Rechnung dupliziert selbst machen.
    if letzte_pruefung_explizit_gesetzt and not naechste_pruefung_explizit_gesetzt:
        basis = pruefzyklus.letzte_pruefung_am or datetime.now(timezone.utc)
        pruefzyklus.naechste_pruefung_am = add_intervall(
            basis, pruefzyklus.intervall_einheit, pruefzyklus.intervall_wert
        )
        pruefzyklus.offener_vorgang_id = None

    await session.flush()
    await session.refresh(pruefzyklus)
    return pruefzyklus


@router.delete(
    "/{pruefzyklus_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("material", "loeschen")),
    ],
)
async def delete_pruefzyklus(
    pruefzyklus_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    bestehend = await session.get(Pruefzyklus, pruefzyklus_id)
    if bestehend is not None:
        await _require_pruefzyklus_zugriff(session, auth, bestehend.anlage_id)
    pruefzyklus = await papierkorb_service.soft_delete(
        session, entity_typ="pruefzyklus", entity_id=pruefzyklus_id, actor_user_id=auth.user_id
    )
    if pruefzyklus is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prüfzyklus nicht gefunden"
        )
