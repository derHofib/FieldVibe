from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_module, require_recht, require_roles
from app.api.routes.auswertung import _nicht_eingeschraenkt
from app.models.user import User
from app.models.vorgang import VORGANG_STATUS, Vorgang
from app.schemas.statistik import (
    AggregatAntwort,
    AggregatBereich,
    AggregatGruppierung,
    AggregatKennzahl,
    TechnikerOffeneVorgaenge,
    VorgangKennzahlen,
)
from app.services.date_utils import add_months
from app.services.statistik_aggregat_service import UngueltigeAbfrage, aggregat_berechnen, pruefe_kombination
from app.services.vorgang_completion_service import VORGANG_STATUS_GESCHLOSSEN
from app.services.zuweisung_service import erlaubte_kunde_ids, erlaubte_user_ids

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
    erlaubte_kunden = await erlaubte_kunde_ids(session, auth)
    if erlaubte_kunden is not None:
        offene_basis = offene_basis.where(Vorgang.kunde_id.in_(erlaubte_kunden))

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
    if erlaubte_kunden is not None:
        je_techniker_stmt = je_techniker_stmt.where(Vorgang.kunde_id.in_(erlaubte_kunden))
    je_techniker_result = await session.execute(je_techniker_stmt)
    je_techniker = [
        TechnikerOffeneVorgaenge(techniker_id=techniker_id, techniker_name=name, anzahl_offen=anzahl)
        for techniker_id, name, anzahl in je_techniker_result.all()
    ]

    # Datensätze mit Abschluss vor Anlage (Altdaten/Demo-Daten) würden den Schnitt
    # ins Negative ziehen -- sie zählen als abgeschlossen, aber nicht in die Zeit.
    durchlaufzeit_stmt = select(
        func.avg(func.extract("epoch", Vorgang.abgeschlossen_am - Vorgang.created_at)).filter(
            Vorgang.abgeschlossen_am >= Vorgang.created_at
        )
        / 86400.0,
        func.count(),
    ).where(Vorgang.geloescht_am.is_(None), Vorgang.abgeschlossen_am.is_not(None))
    if projekt_id:
        durchlaufzeit_stmt = durchlaufzeit_stmt.where(Vorgang.projekt_id == projekt_id)
    if erlaubte_kunden is not None:
        durchlaufzeit_stmt = durchlaufzeit_stmt.where(Vorgang.kunde_id.in_(erlaubte_kunden))
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


# Statistik-Modul wie bei /api/insights und der Zeit-Statistik; nur hier, nicht am
# Router, damit die bestehenden Kennzahlen-Endpunkte unveraendert bleiben.
@router.get(
    "/aggregat",
    response_model=AggregatAntwort,
    dependencies=[Depends(require_module("statistik"))],
)
async def aggregat(
    bereich: AggregatBereich = Query(...),
    kennzahl: AggregatKennzahl = Query(...),
    gruppierung: AggregatGruppierung = Query(...),
    von: date = Query(...),
    bis: date = Query(...),
    techniker_id: UUID | None = Query(default=None),
    kunde_id: UUID | None = Query(default=None),
    projekt_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AggregatAntwort:
    if bereich == "rechnungen":
        # Rechnungsumsaetze unterliegen denselben Sperren wie /api/auswertung --
        # der Router hier prueft nur statistik.
        await require_module("abrechnung")(auth, session)
        await require_recht("abrechnung", "sehen")(auth, session)
        await _nicht_eingeschraenkt(auth, session)
    try:
        pruefe_kombination(bereich, kennzahl, gruppierung)
    except UngueltigeAbfrage as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if bis < von:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="'bis' darf nicht vor 'von' liegen"
        )
    if bis > add_months(von, 36):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Der Zeitraum darf höchstens 3 Jahre umfassen"
        )
    if status_filter is not None and bereich != "vorgaenge":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Der Filter 'status' gilt nur für den Bereich 'vorgaenge'"
        )
    if status_filter is not None and status_filter not in VORGANG_STATUS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unbekannter Status '{status_filter}' (erlaubt: {', '.join(VORGANG_STATUS)})",
        )

    erlaubte_kunden = await erlaubte_kunde_ids(session, auth)
    erlaubte_techniker = (
        await erlaubte_user_ids(session, auth, "mitarbeiterverwaltung", "bearbeiten")
        if kennzahl == "arbeitszeit_stunden" or bereich == "telefonate"
        else None
    )
    try:
        return await aggregat_berechnen(
            session,
            bereich=bereich,
            kennzahl=kennzahl,
            gruppierung=gruppierung,
            von=von,
            bis=bis,
            techniker_id=techniker_id,
            kunde_id=kunde_id,
            projekt_id=projekt_id,
            status=status_filter,
            erlaubte_kunden=erlaubte_kunden,
            erlaubte_techniker=erlaubte_techniker,
        )
    except UngueltigeAbfrage as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
