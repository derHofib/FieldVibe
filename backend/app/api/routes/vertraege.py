from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.anlage import Anlage
from app.models.kunde import Kunde
from app.models.vertrag import Vertrag
from app.schemas.vertrag import VertragCreate, VertragRead, VertragUpdate
from app.services import papierkorb_service

# Nur mandant_admin: disponent und techniker haben laut Rollenmodell
# (Abschnitt 8) keinen Zugriff auf Vertragskonditionen. Da Konditionen ein
# Feld des Vertrags sind (keine separate Tabelle), wird hier der ganze
# Endpunkt statt einzelner Felder eingeschränkt. loesch_operativ (Papierkorb)
# ist die einzige Ausnahme von dieser sonst mitarbeiter-Sichtbarkeit
# nachbildenden Regel: es braucht Zugriff auf diesen Router, um Vertraege
# loeschen/wiederherstellen zu koennen (siehe app/api/routes/papierkorb.py).
router = APIRouter(
    prefix="/api/vertraege",
    tags=["vertraege"],
    dependencies=[Depends(require_roles("mandant_admin", "loesch_operativ"))],
)


@router.get("", response_model=list[VertragRead])
async def list_vertraege(
    kunde_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> list[Vertrag]:
    stmt = select(Vertrag).where(Vertrag.geloescht_am.is_(None)).order_by(Vertrag.bezeichnung)
    if kunde_id:
        stmt = stmt.where(Vertrag.kunde_id == kunde_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "",
    response_model=VertragRead,
    status_code=status.HTTP_201_CREATED,
    # loesch_operativ ist Teil der Router-Basisrolle, aber nur zum Loeschen/
    # Wiederherstellen -- Anlegen/Bearbeiten bleibt mandant_admin vorbehalten.
    dependencies=[Depends(require_roles("mandant_admin"))],
)
async def create_vertrag(
    body: VertragCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Vertrag:
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
                detail="Anlage gehört nicht zum Kunden dieses Vertrags",
            )

    vertrag = Vertrag(
        mandant_id=auth.mandant_id,
        kunde_id=body.kunde_id,
        anlage_id=body.anlage_id,
        bezeichnung=body.bezeichnung,
        abrechnungsart=body.abrechnungsart,
        konditionen=body.konditionen,
        laufzeit_von=body.laufzeit_von,
        laufzeit_bis=body.laufzeit_bis,
    )
    session.add(vertrag)
    await session.flush()
    return vertrag


@router.get("/{vertrag_id}", response_model=VertragRead)
async def get_vertrag(vertrag_id: UUID, session: AsyncSession = Depends(get_db)) -> Vertrag:
    vertrag = await session.get(Vertrag, vertrag_id)
    if vertrag is None or vertrag.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vertrag nicht gefunden")
    return vertrag


@router.patch(
    "/{vertrag_id}",
    response_model=VertragRead,
    dependencies=[Depends(require_roles("mandant_admin"))],
)
async def update_vertrag(
    vertrag_id: UUID, body: VertragUpdate, session: AsyncSession = Depends(get_db)
) -> Vertrag:
    vertrag = await session.get(Vertrag, vertrag_id)
    if vertrag is None or vertrag.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vertrag nicht gefunden")

    # VertragUpdate erlaubt kein Aendern von kunde_id/anlage_id (siehe
    # schemas/vertrag.py) -- die Kunde-Anlage-Konsistenz kann sich nach dem
    # Anlegen eines Vertrags also nur ueber create_vertrag() aendern, dort
    # bereits geprueft.
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(vertrag, field, value)
    await session.flush()
    if changes:
        await session.refresh(vertrag)
    return vertrag


@router.delete("/{vertrag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vertrag(
    vertrag_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    # Papierkorb statt Hard-Delete: kaskadiert auf Vorgaenge, die an diesem
    # Vertrag haengen (siehe app/services/papierkorb_service.py).
    vertrag = await papierkorb_service.soft_delete(
        session, entity_typ="vertrag", entity_id=vertrag_id, actor_user_id=auth.user_id
    )
    if vertrag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vertrag nicht gefunden")
