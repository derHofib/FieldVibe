import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.nav_kategorie import NavKategorie, NavZuordnung
from app.schemas.nav_kategorie import NavKategorienRead, NavKategorienUpdate

router = APIRouter(prefix="/api/nav-kategorien", tags=["nav-kategorien"])


@router.get("", response_model=NavKategorienRead)
async def get_nav_kategorien(
    auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> NavKategorienRead:
    # Fuer JEDE Rolle lesbar (nicht nur mandant_admin) -- die Seitenleiste
    # jedes Nutzers haengt an dieser Gruppierung, siehe office/OfficeLayout.tsx.
    kategorien = (
        (await session.execute(select(NavKategorie).order_by(NavKategorie.reihenfolge)))
        .scalars()
        .all()
    )
    zuordnungen_result = await session.execute(
        select(NavZuordnung.nav_key, NavKategorie.name)
        .join(NavKategorie, NavKategorie.id == NavZuordnung.kategorie_id)
    )
    return NavKategorienRead(
        kategorien=[{"name": k.name, "reihenfolge": k.reihenfolge} for k in kategorien],
        zuordnungen=dict(zuordnungen_result.all()),
    )


@router.put(
    "", response_model=NavKategorienRead, dependencies=[Depends(require_roles("mandant_admin"))]
)
async def set_nav_kategorien(
    body: NavKategorienUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> NavKategorienRead:
    namen = [k.name for k in body.kategorien]
    if len(namen) != len(set(namen)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Kategorie-Namen müssen eindeutig sein"
        )
    unbekannt = set(body.zuordnungen.values()) - set(namen)
    if unbekannt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Zuordnung auf unbekannte Kategorie(n): {', '.join(sorted(unbekannt))}",
        )

    # Volle Ersetzung in fester Reihenfolge, um die FK (RESTRICT) nie zu
    # verletzen: erst alle Zuordnungen weg (loest jede Referenz), dann
    # Kategorien auf den gewuenschten Stand bringen, dann Zuordnungen aus
    # dem Request neu anlegen.
    await session.execute(
        NavZuordnung.__table__.delete().where(NavZuordnung.mandant_id == auth.mandant_id)
    )

    bestehende = (
        (await session.execute(select(NavKategorie).where(NavKategorie.mandant_id == auth.mandant_id)))
        .scalars()
        .all()
    )
    bestehend_nach_name = {k.name: k for k in bestehende}
    name_zu_id: dict[str, uuid.UUID] = {}
    for eintrag in body.kategorien:
        vorhanden = bestehend_nach_name.pop(eintrag.name, None)
        if vorhanden is not None:
            vorhanden.reihenfolge = eintrag.reihenfolge
            name_zu_id[eintrag.name] = vorhanden.id
        else:
            neu = NavKategorie(mandant_id=auth.mandant_id, name=eintrag.name, reihenfolge=eintrag.reihenfolge)
            session.add(neu)
            await session.flush()
            name_zu_id[eintrag.name] = neu.id
    # Was jetzt noch in bestehend_nach_name steht, kam im Request nicht mehr
    # vor -- gehoert geloescht (Zuordnungen sind oben bereits geleert, die
    # FK kann hier nicht mehr blockieren).
    for uebrig in bestehend_nach_name.values():
        await session.delete(uebrig)
    await session.flush()

    for nav_key, kategorie_name in body.zuordnungen.items():
        session.add(
            NavZuordnung(mandant_id=auth.mandant_id, nav_key=nav_key, kategorie_id=name_zu_id[kategorie_name])
        )
    await session.flush()

    return await get_nav_kategorien(auth=auth, session=session)
