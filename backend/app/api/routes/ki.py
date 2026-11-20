"""KI-Zugriff (MCP): Einwilligung zur OAuth-Anfrage und Verwaltung der Verbindungen.
Normale JWT-Auth wie die uebrige API -- der Nutzer meldet sich auf der Einwilligungsseite
des Frontends regulaer an (inkl. MFA). Details: docs/MCP.md."""
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from mcp.server.auth.provider import construct_redirect_uri
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user
from app.core.rollen import MITARBEITER_ROLLEN, ist_mandant_admin
from app.core.security import create_access_token, create_mcp_code
from app.db.session import tenant_session
from app.mcp.oauth_provider import anfrage_pruefen
from app.mcp.zugang import (
    ALLE_SCOPES,
    SCOPE_LESEN,
    SCOPE_SCHREIBEN,
    KiZugang,
    KiZugangAbgelehnt,
    pruefe_ki_zugang,
)
from app.models.ki_verbindung import KiClient, KiVerbindung
from app.models.user import User
from app.schemas.ki import (
    KiAblehnen,
    KiAktionenListe,
    KiAktionRead,
    KiAktionStatus,
    KiAnfrageRead,
    KiAutorisieren,
    KiRedirect,
    KiVerbindungRead,
)
from app.services import ki_journal_service
from app.services.audit_service import log_action
from app.services.ki_rueckgaengig import RueckgaengigAbgelehnt, rueckgaengig

router = APIRouter(prefix="/api/ki", tags=["ki"])


async def _ki_auth(auth: AuthContext = Depends(get_current_user)) -> AuthContext:
    """Vor jedem DB-Zugriff: kein super_admin (kein mandantenuebergreifender KI-Zugriff),
    keine Impersonation, keine Papierkorb-Rollen, kein Aufruf des MCP-Adapters selbst."""
    if (
        auth.role not in MITARBEITER_ROLLEN
        or auth.mandant_id is None
        or auth.impersonated_by is not None
        or auth.via is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="KI-Zugriff gibt es nur für Mitarbeiter-Konten eines Betriebs.",
        )
    return auth


async def _ki_db(request: Request, auth: AuthContext = Depends(_ki_auth)) -> AsyncIterator[AsyncSession]:
    async with tenant_session(mandant_id=auth.mandant_id) as session:
        # Fuer audit_siegel_vor_antwort (app/services/audit_service.py), wie get_db.
        request.state.audit_session = session
        yield session


async def _zugang(session: AsyncSession, auth: AuthContext) -> KiZugang:
    try:
        return await pruefe_ki_zugang(
            session, user_id=auth.user_id, mandant_id=auth.mandant_id, impersonated_by=auth.impersonated_by
        )
    except KiZugangAbgelehnt as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.detail) from exc


def _anfrage(token: str) -> dict:
    try:
        return anfrage_pruefen(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/anfrage", response_model=KiAnfrageRead)
async def anfrage_lesen(
    anfrage: str = Query(min_length=1),
    auth: AuthContext = Depends(_ki_auth),
    session: AsyncSession = Depends(_ki_db),
) -> KiAnfrageRead:
    p = _anfrage(anfrage)
    zugang = await _zugang(session, auth)
    ziel = urlsplit(p["ru"])
    return KiAnfrageRead(
        client_name=p["cn"],
        scopes_angefragt=p["sc"],
        schreiben_erlaubt=zugang.schreiben_erlaubt,
        redirect_host=ziel.hostname or ziel.scheme,
    )


@router.post("/autorisieren", response_model=KiRedirect)
async def autorisieren(
    body: KiAutorisieren,
    auth: AuthContext = Depends(_ki_auth),
    session: AsyncSession = Depends(_ki_db),
) -> KiRedirect:
    p = _anfrage(body.anfrage)
    zugang = await _zugang(session, auth)
    # Nicht auf die angefragten Scopes begrenzt: Claude fragt beim Verbinden nur den Pflicht-
    # Scope an, ueber Schreibzugriff entscheidet der Nutzer hier (gedeckt durch sein Recht).
    unzulaessig = [s for s in body.scopes if s not in ALLE_SCOPES]
    if unzulaessig:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unbekannter Scope: {unzulaessig[0]}"
        )
    if SCOPE_SCHREIBEN in body.scopes and not zugang.schreiben_erlaubt:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dir fehlt das Recht „KI-Assistent (Claude) › bearbeiten“ für Lesen und Schreiben.",
        )
    # Lesen ist die Grundlage jeder Verbindung und immer dabei.
    scopes = [SCOPE_LESEN] + [s for s in ALLE_SCOPES if s != SCOPE_LESEN and s in body.scopes]
    if await session.get(KiClient, p["cid"]) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unbekannter Client.")

    user = zugang.user
    verbindung = KiVerbindung(
        id=uuid4(),
        mandant_id=auth.mandant_id,
        user_id=user.id,
        client_id=p["cid"],
        client_name=p["cn"],
        scopes=scopes,
    )
    session.add(verbindung)
    await session.flush()
    code = create_mcp_code(
        subject=user.id,
        role=user.role,
        mandant_id=auth.mandant_id,
        token_version=user.token_version,
        account_typ_id=user.account_typ_id,
        ki_verbindung_id=verbindung.id,
        scopes=scopes,
        code_challenge=p["cc"],
        redirect_uri=p["ru"],
        redirect_uri_explizit=bool(p.get("rue")),
        client_id=p["cid"],
    )
    await log_action(
        session,
        aktion="ki_verbindung_erteilt",
        mandant_id=auth.mandant_id,
        actor_user_id=user.id,
        entity_type="ki_verbindung",
        entity_id=verbindung.id,
        payload={"client": p["cn"], "scopes": scopes},
    )
    return KiRedirect(redirect_url=construct_redirect_uri(p["ru"], code=code, state=p.get("st")))


@router.post("/ablehnen", response_model=KiRedirect)
async def ablehnen(body: KiAblehnen, _auth: AuthContext = Depends(_ki_auth)) -> KiRedirect:
    p = _anfrage(body.anfrage)
    return KiRedirect(
        redirect_url=construct_redirect_uri(p["ru"], error="access_denied", state=p.get("st"))
    )


@router.get("/verbindungen", response_model=list[KiVerbindungRead])
async def verbindungen_auflisten(
    alle: bool = False,
    auth: AuthContext = Depends(_ki_auth),
    session: AsyncSession = Depends(_ki_db),
) -> list[KiVerbindungRead]:
    if alle and not ist_mandant_admin(auth):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Alle Verbindungen des Betriebs sieht nur ein Mandant-Admin.",
        )
    stmt = (
        select(KiVerbindung, User.name)
        .join(User, User.id == KiVerbindung.user_id)
        .where(KiVerbindung.widerrufen_am.is_(None))
        .order_by(KiVerbindung.erstellt_am.desc())
    )
    if not alle:
        stmt = stmt.where(KiVerbindung.user_id == auth.user_id)
    return [
        KiVerbindungRead(
            id=v.id,
            client_name=v.client_name,
            scopes=v.scopes,
            user_id=v.user_id,
            user_name=name,
            erstellt_am=v.erstellt_am,
            zuletzt_genutzt_am=v.zuletzt_genutzt_am,
        )
        for v, name in (await session.execute(stmt)).all()
    ]


@router.delete("/verbindungen/{verbindung_id}", status_code=status.HTTP_204_NO_CONTENT)
async def verbindung_widerrufen(
    verbindung_id: UUID,
    auth: AuthContext = Depends(_ki_auth),
    session: AsyncSession = Depends(_ki_db),
) -> Response:
    verbindung = await session.get(KiVerbindung, verbindung_id)
    if verbindung is None or (verbindung.user_id != auth.user_id and not ist_mandant_admin(auth)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verbindung nicht gefunden")
    if verbindung.widerrufen_am is None:
        verbindung.widerrufen_am = datetime.now(timezone.utc)
        await log_action(
            session,
            aktion="ki_verbindung_widerrufen",
            mandant_id=auth.mandant_id,
            actor_user_id=auth.user_id,
            entity_type="ki_verbindung",
            entity_id=verbindung.id,
            payload={"client": verbindung.client_name, "nutzer_id": verbindung.user_id},
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Journal (KI-Aktivitaet) ----------------------------------------------------------------------


@router.get("/aktionen", response_model=KiAktionenListe)
async def aktionen_auflisten(
    status_filter: KiAktionStatus | None = Query(default=None, alias="status"),
    user_id: UUID | None = None,
    von: date | None = None,
    bis: date | None = None,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    auth: AuthContext = Depends(_ki_auth),
    session: AsyncSession = Depends(_ki_db),
) -> KiAktionenListe:
    await _zugang(session, auth)
    eintraege, gesamt = await ki_journal_service.auflisten(
        session,
        user_id=auth.user_id,
        ist_admin=ist_mandant_admin(auth),
        status=status_filter,
        filter_user_id=user_id,
        von=von,
        bis=bis,
        q=q,
        limit=limit,
        offset=offset,
    )
    return KiAktionenListe(eintraege=eintraege, gesamt=gesamt)


async def _aktion_lesen(session: AsyncSession, auth: AuthContext, aktion_id: UUID) -> KiAktionRead:
    aktion = await ki_journal_service.lesen(
        session, user_id=auth.user_id, ist_admin=ist_mandant_admin(auth), aktion_id=aktion_id
    )
    if aktion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aktion nicht gefunden")
    return aktion


@router.get("/aktionen/{aktion_id}", response_model=KiAktionRead)
async def aktion_lesen(
    aktion_id: UUID,
    auth: AuthContext = Depends(_ki_auth),
    session: AsyncSession = Depends(_ki_db),
) -> KiAktionRead:
    await _zugang(session, auth)
    return await _aktion_lesen(session, auth, aktion_id)


@router.post("/aktionen/{aktion_id}/rueckgaengig", response_model=KiAktionRead)
async def aktion_rueckgaengig(
    aktion_id: UUID,
    auth: AuthContext = Depends(_ki_auth),
    session: AsyncSession = Depends(_ki_db),
) -> KiAktionRead:
    await _zugang(session, auth)
    # Die Fachrouten laufen in-process mit einem kurzlebigen Token des angemeldeten Nutzers (ohne via=mcp):
    # es zaehlen seine Rechte, nicht die der damaligen KI-Verbindung.
    token = create_access_token(
        subject=auth.user_id,
        role=auth.role,
        mandant_id=auth.mandant_id,
        token_version=auth.token_version,
        account_typ_id=auth.account_typ_id,
        expires_delta=timedelta(minutes=2),
    )
    try:
        await rueckgaengig(
            mandant_id=auth.mandant_id,
            user_id=auth.user_id,
            ist_admin=ist_mandant_admin(auth),
            aktion_id=aktion_id,
            token=token,
            ausloeser="app",
        )
    except RueckgaengigAbgelehnt as exc:
        detail: dict | str = (
            {"meldung": exc.meldung, "konflikte": [k.als_dict() for k in exc.konflikte]}
            if exc.status_code == status.HTTP_409_CONFLICT
            else exc.meldung
        )
        raise HTTPException(status_code=exc.status_code, detail=detail) from exc
    return await _aktion_lesen(session, auth, aktion_id)
