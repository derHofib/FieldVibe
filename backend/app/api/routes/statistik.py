from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_recht, require_roles
from app.models.user import User
from app.models.vorgang import Vorgang
from app.schemas.statistik import TechnikerOffeneVorgaenge, VorgangKennzahlen
from app.services.vorgang_completion_service import VORGANG_STATUS_GESCHLOSSEN

router = APIRouter(
    prefix="/api/statistik",
    tags=["statistik"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("statistik", "sehen")),
    ],
)


@router.get("/vorgang-kennzahlen", response_model=VorgangKennzahlen)
async def vorgang_kennzahlen(
    projekt_id: UUID | None = Query(default=None),
    # Zeitraum bezieht sich nur auf die Durchlaufzeit-Berechnung (welche
    # abgeschlossenen Vorgaenge zaehlen) -- "offene Vorgaenge je Techniker"
    # ist immer eine Momentaufnahme, ein Zeitraum ergibt dort keinen Sinn.
    von: date | None = Query(default=None),
    bis: date | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorgangKennzahlen:
    offene_basis = select(Vorgang).where(
        Vorgang.geloescht_am.is_(None), Vorgang.status.notin_(VORGANG_STATUS_GESCHLOSSEN)
    )
    if projekt_id:
        offene_basis = offene_basis.where(Vorgang.projekt_id == projekt_id)

    gesamt_stmt = select(func.count()).select_from(offene_basis.subquery())
    gesamt_result = await session.execute(gesamt_stmt)
    offene_gesamt = gesamt_result.scalar_one()

    je_techniker_stmt = (
        select(Vorgang.zugewiesener_user_id, User.name, func.count())
        .select_from(Vorgang)
        .join(User, User.id == Vorgang.zugewiesener_user_id)
        .where(
            Vorgang.geloescht_am.is_(None),
            Vorgang.status.notin_(VORGANG_STATUS_GESCHLOSSEN),
            Vorgang.zugewiesener_user_id.is_not(None),
        )
        .group_by(Vorgang.zugewiesener_user_id, User.name)
        .order_by(func.count().desc())
    )
    if projekt_id:
        je_techniker_stmt = je_techniker_stmt.where(Vorgang.projekt_id == projekt_id)
    je_techniker_result = await session.execute(je_techniker_stmt)
    je_techniker = [
        TechnikerOffeneVorgaenge(techniker_id=techniker_id, techniker_name=name, anzahl_offen=anzahl)
        for techniker_id, name, anzahl in je_techniker_result.all()
    ]

    durchlaufzeit_stmt = select(
        func.avg(func.extract("epoch", Vorgang.abgeschlossen_am - Vorgang.created_at)) / 86400.0,
        func.count(),
    ).where(Vorgang.geloescht_am.is_(None), Vorgang.abgeschlossen_am.is_not(None))
    if projekt_id:
        durchlaufzeit_stmt = durchlaufzeit_stmt.where(Vorgang.projekt_id == projekt_id)
    if von:
        durchlaufzeit_stmt = durchlaufzeit_stmt.where(
            Vorgang.abgeschlossen_am >= datetime.combine(von, datetime.min.time(), tzinfo=timezone.utc)
        )
    if bis:
        durchlaufzeit_stmt = durchlaufzeit_stmt.where(
            Vorgang.abgeschlossen_am
            < datetime.combine(bis + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        )
    durchlaufzeit_result = await session.execute(durchlaufzeit_stmt)
    durchschnitt_tage, abgeschlossen_anzahl = durchlaufzeit_result.one()

    return VorgangKennzahlen(
        offene_vorgaenge_gesamt=offene_gesamt,
        offene_vorgaenge_je_techniker=je_techniker,
        durchschnittliche_durchlaufzeit_tage=(
            round(float(durchschnitt_tage), 1) if durchschnitt_tage is not None else None
        ),
        abgeschlossene_vorgaenge_zeitraum=abgeschlossen_anzahl,
    )
