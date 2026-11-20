from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_module, require_recht, require_roles
from app.models.kennzahlen_dashboard import KennzahlenDashboard
from app.models.user import User
from app.schemas.kennzahlen import (
    DashboardAendern,
    DashboardAnlegen,
    DashboardOut,
    DashboardReihenfolge,
    KennzahlDaten,
    KennzahlDef,
)
from app.services import kennzahlen_service

router = APIRouter(
    prefix="/api/kennzahlen",
    tags=["kennzahlen"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_module("statistik")),
        Depends(require_recht("statistik", "sehen")),
    ],
)

_NAME_DOPPELT = "Es gibt bereits ein Dashboard mit diesem Namen"
_NICHT_GEFUNDEN = "Dashboard nicht gefunden"


@router.get("/katalog", response_model=list[KennzahlDef])
async def katalog(
    auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> list[KennzahlDef]:
    return await kennzahlen_service.katalog_fuer(session, auth)


@router.get("/daten", response_model=KennzahlDaten)
async def daten(
    kennzahl: str = Query(...),
    gruppierung: str = Query(default="gesamt"),
    von: date | None = Query(default=None),
    bis: date | None = Query(default=None),
    vergleich_von: date | None = Query(default=None),
    vergleich_bis: date | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> KennzahlDaten:
    try:
        return await kennzahlen_service.kennzahl_daten(
            session, auth, kennzahl, gruppierung, von, bis, vergleich_von, vergleich_bis
        )
    except kennzahlen_service.UnbekannteKennzahl as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except kennzahlen_service.KeinRecht as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except kennzahlen_service.UngueltigeAnfrage as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


def _ist_admin(auth: AuthContext) -> bool:
    return auth.role in ("mandant_admin", "loesch_operativ")


def _out(dashboard: KennzahlenDashboard, ersteller_name: str, auth: AuthContext) -> DashboardOut:
    return DashboardOut(
        id=dashboard.id,
        name=dashboard.name,
        layout=dashboard.layout,
        fuer_alle=dashboard.fuer_alle,
        vorlage=dashboard.vorlage,
        sortierung=dashboard.sortierung,
        eigenes=dashboard.user_id == auth.user_id,
        ersteller_name=ersteller_name,
        updated_at=dashboard.updated_at,
    )


async def _ersteller_name(session: AsyncSession, user_id: UUID) -> str:
    return (await session.execute(select(User.name).where(User.id == user_id))).scalar_one_or_none() or "?"


async def _eigenes_dashboard(session: AsyncSession, auth: AuthContext, dashboard_id: UUID) -> KennzahlenDashboard:
    dashboard = await session.get(KennzahlenDashboard, dashboard_id)
    if dashboard is None or (dashboard.user_id != auth.user_id and not dashboard.fuer_alle):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NICHT_GEFUNDEN)
    if dashboard.user_id != auth.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Geteilte Dashboards kann nur die Ersteller-Person ändern"
        )
    return dashboard


@router.get("/dashboards", response_model=list[DashboardOut])
async def dashboards_auflisten(
    auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> list[DashboardOut]:
    stmt = (
        select(KennzahlenDashboard, User.name)
        .join(User, User.id == KennzahlenDashboard.user_id)
        .where(or_(KennzahlenDashboard.user_id == auth.user_id, KennzahlenDashboard.fuer_alle.is_(True)))
    )
    zeilen = (await session.execute(stmt)).all()
    # Eigene zuerst (nach Tab-Reihenfolge), danach die von anderen geteilten nach Name.
    zeilen.sort(
        key=lambda z: (0, z[0].sortierung, z[0].name) if z[0].user_id == auth.user_id else (1, 0, z[0].name)
    )
    return [_out(dashboard, name, auth) for dashboard, name in zeilen]


@router.post("/dashboards", response_model=DashboardOut, status_code=status.HTTP_201_CREATED)
async def dashboard_anlegen(
    body: DashboardAnlegen,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DashboardOut:
    if body.fuer_alle and not _ist_admin(auth):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nur Administratoren dürfen Dashboards für alle freigeben")
    hoechste = (
        await session.execute(
            select(func.max(KennzahlenDashboard.sortierung)).where(KennzahlenDashboard.user_id == auth.user_id)
        )
    ).scalar_one_or_none()
    dashboard = KennzahlenDashboard(
        mandant_id=auth.mandant_id,
        user_id=auth.user_id,
        name=body.name,
        layout=body.layout.model_dump(mode="json"),
        fuer_alle=body.fuer_alle,
        vorlage=body.vorlage,
        sortierung=(hoechste if hoechste is not None else -1) + 1,
    )
    session.add(dashboard)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_NAME_DOPPELT) from exc
    await session.refresh(dashboard)
    return _out(dashboard, await _ersteller_name(session, dashboard.user_id), auth)


# Vor /dashboards/{id}, sonst faengt der Pfadparameter "reihenfolge" ab.
@router.put("/dashboards/reihenfolge", response_model=list[DashboardOut])
async def dashboards_reihenfolge(
    body: DashboardReihenfolge,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[DashboardOut]:
    eigene = {
        d.id: d
        for d in (
            await session.execute(select(KennzahlenDashboard).where(KennzahlenDashboard.user_id == auth.user_id))
        ).scalars()
    }
    position = 0
    for dashboard_id in body.ids:
        dashboard = eigene.pop(dashboard_id, None)
        if dashboard is not None:
            dashboard.sortierung = position
            position += 1
    # Nicht genannte eigene Dashboards rutschen in bisheriger Reihenfolge ans Ende.
    for dashboard in sorted(eigene.values(), key=lambda d: (d.sortierung, d.name)):
        dashboard.sortierung = position
        position += 1
    await session.flush()
    return await dashboards_auflisten(auth, session)


@router.patch("/dashboards/{dashboard_id}", response_model=DashboardOut)
async def dashboard_aendern(
    dashboard_id: UUID,
    body: DashboardAendern,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DashboardOut:
    dashboard = await _eigenes_dashboard(session, auth, dashboard_id)
    aenderungen = body.model_dump(exclude_unset=True)
    if aenderungen.get("fuer_alle") and not _ist_admin(auth):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nur Administratoren dürfen Dashboards für alle freigeben")
    if body.name is not None:
        dashboard.name = body.name
    if body.layout is not None:
        dashboard.layout = body.layout.model_dump(mode="json")
    if body.fuer_alle is not None:
        dashboard.fuer_alle = body.fuer_alle
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_NAME_DOPPELT) from exc
    await session.refresh(dashboard)
    return _out(dashboard, await _ersteller_name(session, dashboard.user_id), auth)


@router.delete("/dashboards/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def dashboard_loeschen(
    dashboard_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    dashboard = await _eigenes_dashboard(session, auth, dashboard_id)
    await session.delete(dashboard)
    await session.flush()
