from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.models.kunde import Kunde
from app.models.kunde_zuweisung import KundeZuweisung
from app.models.user import User
from app.schemas.techniker_uebersicht import TechnikerZuweisungUebersicht

router = APIRouter(
    prefix="/api/techniker-zuweisungen",
    tags=["techniker-zuweisungen"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)


@router.get("", response_model=list[TechnikerZuweisungUebersicht])
async def uebersicht(session: AsyncSession = Depends(get_db)) -> list[TechnikerZuweisungUebersicht]:
    """Fuer den Disponent: welcher Techniker betreut welche Kunden.
    Zeigt auch Techniker ohne Zuweisungen (leere Kunden-Liste)."""
    techniker_result = await session.execute(
        select(User).where(User.role == "techniker").order_by(User.name)
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
