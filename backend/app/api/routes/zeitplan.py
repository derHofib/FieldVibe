from collections.abc import Awaitable, Callable
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_module, require_recht, require_roles
from app.api.routes.projekte import _require_projekt
from app.models.mandant import Mandant
from app.models.user import User
from app.schemas.projekt import (
    ProjektVorlageAusProjekt,
    ProjektVorlageDetail,
    ProjektVorlageListe,
    ProjektVorlageUpdate,
    ZeitplanBasisplanCreate,
    ZeitplanBasisplanRead,
    ZeitplanStraffenRead,
    ZeitplanStraffenRequest,
    ZeitplanVorlageAnwenden,
    ZeitplanAbhaengigkeitCreate,
    ZeitplanAbhaengigkeitUpdate,
    ZeitplanBestellungAuswahl,
    ZeitplanEinstellungenUpdate,
    ZeitplanElementCreate,
    ZeitplanElementUpdate,
    ZeitplanRead,
    ZeitplanVorgangAuswahl,
)
from app.schemas.zeitplan_antrag import (
    ZeitplanAntragAblehnen,
    ZeitplanAntragAnnehmen,
    ZeitplanAntragCreate,
    ZeitplanAntragEntscheidungRead,
    ZeitplanAntragRead,
    ZeitplanAntragStatus,
    ZeitplanMeinRead,
)
from app.services import zeitplan_antrag_service as antrag_svc
from app.services import zeitplan_service as svc
from app.services.rechte_service import hat_recht
from app.services.pdf_service import generate_zeitplan_pdf
from app.services.rechnung_service import logo_bytes_laden
from app.services.zuweisung_service import erlaubte_kunde_ids

# Lesen wie die uebrigen Projekt-Routen; jede Mutation braucht zusaetzlich
# "bearbeiten" (siehe _SCHREIBEN) und liefert den kompletten Zeitplan zurueck.
async def _erlaubte_kunden_merken(
    auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> None:
    session.info[svc.ERLAUBTE_KUNDEN_INFO_KEY] = await erlaubte_kunde_ids(session, auth)


def _recht_eines_von(*rechte: tuple[str, str]):
    """Wie require_recht, aber ODER ueber mehrere (bereich, aktion)-Paare --
    Techniker haben typischerweise nur projekte.zeitplan_sehen statt
    projekte.sehen."""

    async def checker(
        auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
    ) -> AuthContext:
        if auth.role != "custom":
            return auth
        for bereich, aktion in rechte:
            if await hat_recht(session, account_typ_id=auth.account_typ_id, user_id=auth.user_id, bereich=bereich, aktion=aktion):
                return auth
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Keine Berechtigung für diese Aktion")

    return checker


async def _darf_projekte_sehen(session: AsyncSession, auth: AuthContext) -> bool:
    return auth.role != "custom" or await hat_recht(
        session, account_typ_id=auth.account_typ_id, user_id=auth.user_id, bereich="projekte", aktion="sehen"
    )


async def _darf_bearbeiten(session: AsyncSession, auth: AuthContext) -> bool:
    return auth.role != "custom" or await hat_recht(
        session, account_typ_id=auth.account_typ_id, user_id=auth.user_id, bereich="projekte", aktion="bearbeiten"
    )


# Router-Ebene nur Rolle + Kunden-Schwaerzung; das Recht haengt je Route an
# _LESEN (Zeitplan ansehen) bzw. _SEHEN (Editor-Hilfslisten, nur projekte.sehen).
router = APIRouter(
    prefix="/api/projekte/{projekt_id}/zeitplan",
    tags=["projekte"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(_erlaubte_kunden_merken),
    ],
)

_LESEN = [Depends(_recht_eines_von(("projekte", "sehen"), ("projekte", "zeitplan_sehen")))]


async def _mitarbeit_noetig(
    projekt_id: UUID, auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> None:
    """Ohne projekte.sehen nur Projekte mit Mitarbeit; 404 statt 403, damit die
    Existenz fremder Projekte nicht verraten wird."""
    if await _darf_projekte_sehen(session, auth):
        return
    if not await antrag_svc.hat_mitarbeit(session, auth.user_id, projekt_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projekt nicht gefunden")


_PROJEKT_LESEN = [*_LESEN, Depends(_mitarbeit_noetig)]
_SEHEN = [Depends(require_recht("projekte", "sehen"))]
_SCHREIBEN = [
    Depends(require_roles("mandant_admin", "custom")),
    Depends(require_recht("projekte", "sehen")),
    Depends(require_recht("projekte", "bearbeiten")),
]
_BEANTRAGEN = [
    Depends(require_roles("mandant_admin", "custom")),
    Depends(_recht_eines_von(("projekte", "zeitplan_beantragen"), ("projekte", "bearbeiten"))),
]

_STATUS = {
    svc.ZeitplanRegelverstoss: status.HTTP_400_BAD_REQUEST,
    svc.ZeitplanNichtGefunden: status.HTTP_404_NOT_FOUND,
    svc.ZeitplanZyklus: status.HTTP_409_CONFLICT,
    svc.ZeitplanDuplikat: status.HTTP_409_CONFLICT,
    antrag_svc.AntragKonflikt: status.HTTP_409_CONFLICT,
    antrag_svc.AntragNichtErlaubt: status.HTTP_403_FORBIDDEN,
}


def _fehler(exc: svc.ZeitplanFehler) -> HTTPException:
    return HTTPException(status_code=_STATUS[type(exc)], detail=str(exc))


async def _ausfuehren(
    session: AsyncSession, projekt_id: UUID, aktion: Callable[..., Awaitable[None]]
) -> ZeitplanRead:
    projekt = await _require_projekt(session, projekt_id)
    try:
        await aktion(projekt)
    except svc.ZeitplanFehler as exc:
        raise HTTPException(status_code=_STATUS[type(exc)], detail=str(exc)) from exc
    return await svc.lese_zeitplan(session, projekt)


async def _lese(session: AsyncSession, projekt, basisplan_id: UUID | None) -> ZeitplanRead:
    try:
        return await svc.lese_zeitplan(session, projekt, basisplan_id)
    except svc.ZeitplanFehler as exc:
        raise HTTPException(status_code=_STATUS[type(exc)], detail=str(exc)) from exc


@router.get("", response_model=ZeitplanRead, dependencies=_PROJEKT_LESEN)
async def get_zeitplan(
    projekt_id: UUID, basisplan_id: UUID | None = None, session: AsyncSession = Depends(get_db)
) -> ZeitplanRead:
    projekt = await _require_projekt(session, projekt_id)
    return await _lese(session, projekt, basisplan_id)


@router.get("/pdf", dependencies=_PROJEKT_LESEN)
async def get_zeitplan_pdf(
    projekt_id: UUID,
    basisplan_id: UUID | None = None,
    kritischer_pfad: bool = True,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    projekt = await _require_projekt(session, projekt_id)
    zeitplan = await _lese(session, projekt, basisplan_id)
    basisplan_name = None
    if basisplan_id is not None:
        basisplan_name = next(b.name for b in await svc.basisplaene_lesen(session, projekt) if b.id == basisplan_id)
    mandant = await session.get(Mandant, auth.mandant_id)
    pdf_bytes = generate_zeitplan_pdf(
        mandant,
        projekt.name,
        zeitplan,
        basisplan_name=basisplan_name,
        kritischer_pfad=kritischer_pfad,
        logo_bytes=await logo_bytes_laden(mandant),
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="zeitplan.pdf"'},
    )


@router.get("/basisplaene", response_model=list[ZeitplanBasisplanRead], dependencies=_PROJEKT_LESEN)
async def list_basisplaene(projekt_id: UUID, session: AsyncSession = Depends(get_db)) -> list[ZeitplanBasisplanRead]:
    projekt = await _require_projekt(session, projekt_id)
    return await svc.basisplaene_lesen(session, projekt)


@router.post(
    "/basisplaene",
    response_model=ZeitplanBasisplanRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=_SCHREIBEN,
)
async def create_basisplan(
    projekt_id: UUID,
    body: ZeitplanBasisplanCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ZeitplanBasisplanRead:
    projekt = await _require_projekt(session, projekt_id)
    try:
        return await svc.basisplan_erstellen(
            session, projekt, mandant_id=auth.mandant_id, user_id=auth.user_id, name=body.name
        )
    except svc.ZeitplanFehler as exc:
        raise HTTPException(status_code=_STATUS[type(exc)], detail=str(exc)) from exc


@router.delete("/basisplaene/{basisplan_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=_SCHREIBEN)
async def delete_basisplan(projekt_id: UUID, basisplan_id: UUID, session: AsyncSession = Depends(get_db)) -> Response:
    projekt = await _require_projekt(session, projekt_id)
    try:
        await svc.basisplan_loeschen(session, projekt, basisplan_id)
    except svc.ZeitplanFehler as exc:
        raise HTTPException(status_code=_STATUS[type(exc)], detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/straffen", response_model=ZeitplanStraffenRead, dependencies=_SCHREIBEN)
async def straffen(
    projekt_id: UUID, body: ZeitplanStraffenRequest, session: AsyncSession = Depends(get_db)
) -> ZeitplanStraffenRead:
    projekt = await _require_projekt(session, projekt_id)
    try:
        aenderungen = await svc.straffen(session, projekt, body.phase_id, body.vorschau)
    except svc.ZeitplanFehler as exc:
        raise HTTPException(status_code=_STATUS[type(exc)], detail=str(exc)) from exc
    return ZeitplanStraffenRead(
        aenderungen=aenderungen, zeitplan=None if body.vorschau else await svc.lese_zeitplan(session, projekt)
    )


@router.post("/vorlage-anwenden", response_model=ZeitplanRead, dependencies=_SCHREIBEN)
async def vorlage_anwenden(
    projekt_id: UUID,
    body: ZeitplanVorlageAnwenden,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ZeitplanRead:
    return await _ausfuehren(
        session,
        projekt_id,
        lambda projekt: svc.vorlage_anwenden(
            session,
            projekt,
            mandant_id=auth.mandant_id,
            user_id=auth.user_id,
            vorlage_id=body.vorlage_id,
            start_am=body.start_am,
        ),
    )


@router.get("/auswahl/vorgaenge", response_model=list[ZeitplanVorgangAuswahl], dependencies=_SEHEN)
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
    dependencies=[
        *_SEHEN,
        Depends(require_module("material")),
        Depends(require_recht("material", "sehen")),
    ],
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


# --- Aenderungsantraege (Techniker) -----------------------------------------


async def _entscheidung(session: AsyncSession, projekt, antrag_id: UUID) -> ZeitplanAntragEntscheidungRead:
    return ZeitplanAntragEntscheidungRead(
        antrag=await antrag_svc.lese_einen(session, projekt.id, antrag_id),
        zeitplan=await svc.lese_zeitplan(session, projekt),
    )


async def _antrag_ausfuehren(session: AsyncSession, projekt_id: UUID, antrag_id: UUID, aktion):
    projekt = await _require_projekt(session, projekt_id)
    try:
        await aktion(projekt)
    except svc.ZeitplanFehler as exc:
        raise _fehler(exc) from exc
    return await _entscheidung(session, projekt, antrag_id)


@router.post(
    "/antraege",
    response_model=ZeitplanAntragRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[*_PROJEKT_LESEN, *_BEANTRAGEN],
)
async def create_antrag(
    projekt_id: UUID,
    body: ZeitplanAntragCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ZeitplanAntragRead:
    projekt = await _require_projekt(session, projekt_id)
    user = await session.get(User, auth.user_id)
    try:
        antrag = await antrag_svc.erstellen(session, projekt, mandant_id=auth.mandant_id, user=user, body=body)
    except svc.ZeitplanFehler as exc:
        raise _fehler(exc) from exc
    return await antrag_svc.lese_einen(session, projekt.id, antrag.id)


@router.get("/antraege", response_model=list[ZeitplanAntragRead], dependencies=_PROJEKT_LESEN)
async def list_antraege(
    projekt_id: UUID,
    status_filter: ZeitplanAntragStatus | None = Query(default=None, alias="status"),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[ZeitplanAntragRead]:
    await _require_projekt(session, projekt_id)
    # Ohne Schreibrecht nur die eigenen Antraege -- die Antworten/Namen anderer
    # Techniker gehen sie nichts an.
    nur_von = None if await _darf_bearbeiten(session, auth) else auth.user_id
    return await antrag_svc.lesen(session, projekt_id, nur_von=nur_von, status=status_filter)


@router.post(
    "/antraege/{antrag_id}/annehmen", response_model=ZeitplanAntragEntscheidungRead, dependencies=_SCHREIBEN
)
async def annehmen_antrag(
    projekt_id: UUID,
    antrag_id: UUID,
    body: ZeitplanAntragAnnehmen | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ZeitplanAntragEntscheidungRead:
    user = await session.get(User, auth.user_id)
    erlaubte = await erlaubte_kunde_ids(session, auth)
    antwort = (body.antwort or "").strip() or None if body else None
    return await _antrag_ausfuehren(
        session,
        projekt_id,
        antrag_id,
        lambda projekt: antrag_svc.annehmen(
            session, projekt, antrag_id, user=user, antwort=antwort, erlaubte_kunden=erlaubte
        ),
    )


@router.post(
    "/antraege/{antrag_id}/ablehnen", response_model=ZeitplanAntragEntscheidungRead, dependencies=_SCHREIBEN
)
async def ablehnen_antrag(
    projekt_id: UUID,
    antrag_id: UUID,
    body: ZeitplanAntragAblehnen,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ZeitplanAntragEntscheidungRead:
    user = await session.get(User, auth.user_id)
    return await _antrag_ausfuehren(
        session,
        projekt_id,
        antrag_id,
        lambda projekt: antrag_svc.ablehnen(session, projekt, antrag_id, user=user, antwort=body.antwort),
    )


@router.post(
    "/antraege/{antrag_id}/zurueckziehen", response_model=ZeitplanAntragEntscheidungRead, dependencies=_PROJEKT_LESEN
)
async def zurueckziehen_antrag(
    projekt_id: UUID,
    antrag_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ZeitplanAntragEntscheidungRead:
    user = await session.get(User, auth.user_id)
    return await _antrag_ausfuehren(
        session, projekt_id, antrag_id, lambda projekt: antrag_svc.zurueckziehen(session, projekt, antrag_id, user=user)
    )


# Eigener Router: /api/projekte/meine-zeitplaene muss VOR projekte.router
# registriert werden (siehe main.py), sonst faengt /{projekt_id} den Pfad ab.
meine_router = APIRouter(
    prefix="/api/projekte",
    tags=["projekte"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        *_LESEN,
    ],
)


@meine_router.get("/meine-zeitplaene", response_model=list[ZeitplanMeinRead])
async def meine_zeitplaene(
    auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> list[ZeitplanMeinRead]:
    return await antrag_svc.meine_zeitplaene(
        session, auth.user_id, alle=await _darf_projekte_sehen(session, auth), heute=date.today()
    )


# Projektvorlagen: mandantenweit, daher eigener Router ohne Projekt im Pfad.
vorlagen_router = APIRouter(
    prefix="/api/projekt-vorlagen",
    tags=["projekte"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("projekte", "sehen")),
    ],
)


@vorlagen_router.get("", response_model=list[ProjektVorlageListe])
async def list_vorlagen(session: AsyncSession = Depends(get_db)) -> list[ProjektVorlageListe]:
    return await svc.vorlagen_lesen(session)


@vorlagen_router.get("/{vorlage_id}", response_model=ProjektVorlageDetail)
async def get_vorlage(vorlage_id: UUID, session: AsyncSession = Depends(get_db)) -> ProjektVorlageDetail:
    try:
        return await svc.vorlage_detail(session, vorlage_id)
    except svc.ZeitplanFehler as exc:
        raise _fehler(exc) from exc


@vorlagen_router.post(
    "/aus-projekt/{projekt_id}",
    response_model=ProjektVorlageDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=_SCHREIBEN,
)
async def create_vorlage_aus_projekt(
    projekt_id: UUID,
    body: ProjektVorlageAusProjekt,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ProjektVorlageDetail:
    projekt = await _require_projekt(session, projekt_id)
    try:
        vorlage_id = await svc.vorlage_aus_projekt(
            session,
            projekt,
            mandant_id=auth.mandant_id,
            user_id=auth.user_id,
            name=body.name,
            beschreibung=body.beschreibung,
        )
        return await svc.vorlage_detail(session, vorlage_id)
    except svc.ZeitplanFehler as exc:
        raise _fehler(exc) from exc


@vorlagen_router.patch("/{vorlage_id}", response_model=ProjektVorlageDetail, dependencies=_SCHREIBEN)
async def update_vorlage(
    vorlage_id: UUID, body: ProjektVorlageUpdate, session: AsyncSession = Depends(get_db)
) -> ProjektVorlageDetail:
    try:
        await svc.vorlage_aendern(session, vorlage_id, body.model_dump(exclude_unset=True))
        return await svc.vorlage_detail(session, vorlage_id)
    except svc.ZeitplanFehler as exc:
        raise _fehler(exc) from exc


@vorlagen_router.delete("/{vorlage_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=_SCHREIBEN)
async def delete_vorlage(vorlage_id: UUID, session: AsyncSession = Depends(get_db)) -> Response:
    try:
        await svc.vorlage_loeschen(session, vorlage_id)
    except svc.ZeitplanFehler as exc:
        raise _fehler(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
