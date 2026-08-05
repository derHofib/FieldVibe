from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_recht, require_roles
from app.models.kunde import Kunde
from app.models.kunde_zuweisung import KundeZuweisung
from app.models.user import User
from app.schemas.techniker_uebersicht import TechnikerZuweisungUebersicht
from app.services.zuweisung_service import technik_user_ids

router = APIRouter(
    prefix="/api/techniker-zuweisungen",
    tags=["techniker-zuweisungen"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("kunden", "bearbeiten")),
    ],
)


@router.get("", response_model=list[TechnikerZuweisungUebersicht])
async def uebersicht(
    auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> list[TechnikerZuweisungUebersicht]:
    """Fuer den Disponent: welcher Techniker betreut welche Kunden.
    Zeigt auch Techniker ohne Zuweisungen (leere Kunden-Liste)."""
    techniker_ids = await technik_user_ids(session, auth.mandant_id)
    techniker_result = await session.execute(
        select(User).where(User.id.in_(techniker_ids)).order_by(User.name)
    )
    techniker_liste = list(techniker_result.scalars().all())

    zuweisungen_result = await session.execute(
        select(KundeZuweisung.user_id, Kunde)
        .join(Kunde, Kunde.id == KundeZuweisung.kunde_id)
        .order_by(Kunde.name)
    )
    kunden_by_user: dict = {}
    for user_id, kunde in zuweisungen_result.all():
        kunden_by_user.setdefault(user_id, []).append(kunde)

    return [
        TechnikerZuweisungUebersicht(
            techniker=techniker, kunden=kunden_by_user.get(techniker.id, [])
        )
        for techniker in techniker_liste
    ]
