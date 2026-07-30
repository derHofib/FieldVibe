from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.anlage import Anlage
from app.models.fahrzeug_zuweisung import FahrzeugZuweisung
from app.models.user import User
from app.schemas.anlage import AnlageRead
from app.schemas.fahrzeug_zuweisung import FahrzeugZuweisungSetzen, FahrzeugZuweisungUebersicht
from app.schemas.user import UserRead

router = APIRouter(
    prefix="/api/fahrzeug-zuweisungen",
    tags=["fahrzeug-zuweisungen"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)


async def _zuweisung_fuer(session: AsyncSession, user_id: UUID) -> FahrzeugZuweisung | None:
    result = await session.execute(
        select(FahrzeugZuweisung).where(FahrzeugZuweisung.user_id == user_id)
    )
    return result.scalar_one_or_none()


@router.get(
    "",
    response_model=list[FahrzeugZuweisungUebersicht],
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def uebersicht(session: AsyncSession = Depends(get_db)) -> list[FahrzeugZuweisungUebersicht]:
    """Fuer den Disponent: welcher Techniker faehrt welches Fahrzeug.
    Zeigt auch Techniker ohne Zuweisung (fahrzeug=None)."""
    techniker_result = await session.execute(
        select(User).where(User.role == "techniker").order_by(User.name)
    )
    techniker_liste = list(techniker_result.scalars().all())

    zuweisungen_result = await session.execute(
        select(FahrzeugZuweisung.user_id, Anlage).join(Anlage, Anlage.id == FahrzeugZuweisung.anlage_id)
    )
    fahrzeug_by_user = {user_id: anlage for user_id, anlage in zuweisungen_result.all()}

    return [
        FahrzeugZuweisungUebersicht(
            techniker=UserRead.model_validate(techniker),
            fahrzeug=(
                AnlageRead.model_validate(fahrzeug_by_user[techniker.id])
                if techniker.id in fahrzeug_by_user
                else None
            ),
        )
        for techniker in techniker_liste
    ]


@router.get("/mir", response_model=AnlageRead | None)
async def meine_zuweisung(
    auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> Anlage | None:
    """Fuer die App selbst: das eigene zugewiesene Fahrzeug, um es als
    Standard-Lagerort beim Material-Verbrauch vorzuschlagen."""
    zuweisung = await _zuweisung_fuer(session, auth.user_id)
    if zuweisung is None:
        return None
    return await session.get(Anlage, zuweisung.anlage_id)


@router.put(
    "/{user_id}",
    response_model=AnlageRead | None,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def zuweisung_setzen(
    user_id: UUID,
    body: FahrzeugZuweisungSetzen,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Anlage | None:
    techniker = await session.get(User, user_id)
    if techniker is None or techniker.role != "techniker":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Techniker nicht gefunden"
        )

    bestehende = await _zuweisung_fuer(session, user_id)

    if body.anlage_id is None:
        if bestehende is not None:
            await session.delete(bestehende)
            await session.flush()
        return None

    fahrzeug = await session.get(Anlage, body.anlage_id)
    if fahrzeug is None or fahrzeug.objekttyp != "fahrzeug":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Fahrzeug nicht gefunden"
        )

    if bestehende is not None:
        bestehende.anlage_id = fahrzeug.id
    else:
        session.add(
            FahrzeugZuweisung(mandant_id=auth.mandant_id, user_id=user_id, anlage_id=fahrzeug.id)
        )
    await session.flush()
    return fahrzeug
