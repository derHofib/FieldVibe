from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_module, require_recht, require_roles
from app.api.routes.projekte import _require_projekt
from app.schemas.projekt import (
    ZeitplanAbhaengigkeitCreate,
    ZeitplanAbhaengigkeitUpdate,
    ZeitplanBestellungAuswahl,
    ZeitplanEinstellungenUpdate,
    ZeitplanElementCreate,
    ZeitplanElementUpdate,
    ZeitplanRead,
    ZeitplanVorgangAuswahl,
)
from app.services import zeitplan_service as svc
from app.services.zuweisung_service import erlaubte_kunde_ids

# Lesen wie die uebrigen Projekt-Routen; jede Mutation braucht zusaetzlich
# "bearbeiten" (siehe _SCHREIBEN) und liefert den kompletten Zeitplan zurueck.
router = APIRouter(
    prefix="/api/projekte/{projekt_id}/zeitplan",
    tags=["projekte"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("projekte", "sehen")),
    ],
)

_SCHREIBEN = [
    Depends(require_roles("mandant_admin", "custom")),
    Depends(require_recht("projekte", "bearbeiten")),
]

_STATUS = {
    svc.ZeitplanRegelverstoss: status.HTTP_400_BAD_REQUEST,
    svc.ZeitplanNichtGefunden: status.HTTP_404_NOT_FOUND,
    svc.ZeitplanZyklus: status.HTTP_409_CONFLICT,
    svc.ZeitplanDuplikat: status.HTTP_409_CONFLICT,
}


async def _ausfuehren(
    session: AsyncSession, projekt_id: UUID, aktion: Callable[..., Awaitable[None]]
) -> ZeitplanRead:
    projekt = await _require_projekt(session, projekt_id)
    try:
        await aktion(projekt)
    except svc.ZeitplanFehler as exc:
        raise HTTPException(status_code=_STATUS[type(exc)], detail=str(exc)) from exc
    return await svc.lese_zeitplan(session, projekt)


@router.get("", response_model=ZeitplanRead)
async def get_zeitplan(projekt_id: UUID, session: AsyncSession = Depends(get_db)) -> ZeitplanRead:
    projekt = await _require_projekt(session, projekt_id)
    return await svc.lese_zeitplan(session, projekt)


@router.get("/auswahl/vorgaenge", response_model=list[ZeitplanVorgangAuswahl])
async def auswahl_vorgaenge(
    projekt_id: UUID,
    q: str | None = None,
    limit: int = Query(default=30, ge=1, le=100),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[ZeitplanVorgangAuswahl]:
    projekt = await _require_projekt(session, projekt_id)
    return await svc.auswahl_vorgaenge(session, projekt, q, limit, await erlaubte_kunde_ids(session, auth))


@router.get(
    "/auswahl/bestellungen",
    response_model=list[ZeitplanBestellungAuswahl],
    dependencies=[Depends(require_module("material")), Depends(require_recht("material", "sehen"))],
)
async def auswahl_bestellungen(
    projekt_id: UUID,
    q: str | None = None,
    limit: int = Query(default=30, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> list[ZeitplanBestellungAuswahl]:
    await _require_projekt(session, projekt_id)
    return await svc.auswahl_bestellungen(session, q, limit)


@router.post("/elemente", response_model=ZeitplanRead, dependencies=_SCHREIBEN)
async def create_element(
    projekt_id: UUID,
    body: ZeitplanElementCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ZeitplanRead:
    erlaubte = await erlaubte_kunde_ids(session, auth)
    return await _ausfuehren(
        session,
        projekt_id,
        lambda projekt: svc.element_anlegen(
            session,
            projekt,
            mandant_id=auth.mandant_id,
            user_id=auth.user_id,
            typ=body.typ,
            titel=body.titel,
            phase_id=body.phase_id,
            start_am=body.start_am,
            ende_am=body.ende_am,
            zugewiesen_an=body.zugewiesen_an,
            vorgang_id=body.vorgang_id,
            bestellung_id=body.bestellung_id,
            partner_id=body.partner_id,
            erlaubte_kunden=erlaubte,
        ),
    )


@router.patch("/elemente/{element_id}", response_model=ZeitplanRead, dependencies=_SCHREIBEN)
async def update_element(
    projekt_id: UUID,
    element_id: UUID,
    body: ZeitplanElementUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ZeitplanRead:
    erlaubte = await erlaubte_kunde_ids(session, auth)
    return await _ausfuehren(
        session,
        projekt_id,
        lambda projekt: svc.element_aendern(
            session, projekt, element_id, body.model_dump(exclude_unset=True), auth.mandant_id, erlaubte
        ),
    )


@router.delete("/elemente/{element_id}", response_model=ZeitplanRead, dependencies=_SCHREIBEN)
async def delete_element(
    projekt_id: UUID,
    element_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ZeitplanRead:
    return await _ausfuehren(
        session, projekt_id, lambda projekt: svc.element_loeschen(session, projekt, element_id, auth.user_id)
    )


@router.post("/abhaengigkeiten", response_model=ZeitplanRead, dependencies=_SCHREIBEN)
async def create_abhaengigkeit(
    projekt_id: UUID,
    body: ZeitplanAbhaengigkeitCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ZeitplanRead:
    return await _ausfuehren(
        session,
        projekt_id,
        lambda projekt: svc.abhaengigkeit_anlegen(
            session,
            projekt,
            mandant_id=auth.mandant_id,
            user_id=auth.user_id,
            vorgaenger_id=body.vorgaenger_id,
            nachfolger_id=body.nachfolger_id,
            versatz_tage=body.versatz_tage,
            art=body.art,
        ),
    )


@router.patch("/abhaengigkeiten/{abhaengigkeit_id}", response_model=ZeitplanRead, dependencies=_SCHREIBEN)
async def update_abhaengigkeit(
    projekt_id: UUID,
    abhaengigkeit_id: UUID,
    body: ZeitplanAbhaengigkeitUpdate,
    session: AsyncSession = Depends(get_db),
) -> ZeitplanRead:
    return await _ausfuehren(
        session,
        projekt_id,
        lambda projekt: svc.abhaengigkeit_aendern(
            session, projekt, abhaengigkeit_id, versatz_tage=body.versatz_tage, art=body.art
        ),
    )


@router.delete("/abhaengigkeiten/{abhaengigkeit_id}", response_model=ZeitplanRead, dependencies=_SCHREIBEN)
async def delete_abhaengigkeit(
    projekt_id: UUID, abhaengigkeit_id: UUID, session: AsyncSession = Depends(get_db)
) -> ZeitplanRead:
    return await _ausfuehren(
        session, projekt_id, lambda projekt: svc.abhaengigkeit_loeschen(session, projekt, abhaengigkeit_id)
    )


@router.patch("/einstellungen", response_model=ZeitplanRead, dependencies=_SCHREIBEN)
async def update_einstellungen(
    projekt_id: UUID, body: ZeitplanEinstellungenUpdate, session: AsyncSession = Depends(get_db)
) -> ZeitplanRead:
    return await _ausfuehren(
        session, projekt_id, lambda projekt: svc.modus_setzen(session, projekt, body.verschiebe_modus)
    )
