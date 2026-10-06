import hashlib
import hmac
import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.api.deps import AuthContext, get_db, require_recht, require_roles
from app.core.config import get_settings
from app.core.rollen import ist_plattform_admin
from app.core.rate_limit import client_ip, fehlerbericht_service_ip_limiter, fehlerbericht_user_limiter
from app.db.session import system_session
from app.models.fehlerbericht import Fehlerbericht
from app.schemas.fehlerbericht import (
    FehlerberichtArt,
    FehlerberichtCreate,
    FehlerberichtCreated,
    FehlerberichtDetail,
    FehlerberichtListItem,
    FehlerberichtSchweregrad,
    FehlerberichtServiceUpdate,
    FehlerberichtStatus,
    FehlerberichtUpdate,
    FehlerberichtZaehler,
)
from app.services import audit_service, fehlerbericht_service, storage_service

_PAYLOAD_PARSE_MAX_BYTES = 4 * 1024 * 1024
_ROLLEN = ("super_admin", "mandant_admin", "custom")

router = APIRouter(prefix="/api/fehlerberichte", tags=["fehlerberichte"])
service_router = APIRouter(prefix="/api/service/fehlerberichte", tags=["fehlerberichte: service-api"])


def _gefiltert(
    stmt,
    *,
    status_: str | None,
    schweregrad: str | None,
    art: str | None = None,
    seit: datetime | None,
    q: str | None = None,
):
    if status_:
        stmt = stmt.where(Fehlerbericht.status == status_)
    if schweregrad:
        stmt = stmt.where(Fehlerbericht.schweregrad == schweregrad)
    if art:
        stmt = stmt.where(Fehlerbericht.art == art)
    if seit is not None:
        stmt = stmt.where(Fehlerbericht.created_at >= (seit if seit.tzinfo else seit.replace(tzinfo=timezone.utc)))
    if q:
        muster = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(
            or_(Fehlerbericht.titel.ilike(muster, escape="\\"), Fehlerbericht.beschreibung.ilike(muster, escape="\\"))
        )
    return stmt


async def _liste_antwort(session: AsyncSession, stmt) -> list[FehlerberichtListItem]:
    berichte = list((await session.execute(stmt)).scalars().all())
    mandanten, users = await fehlerbericht_service.namen_laden(session, berichte)
    return [fehlerbericht_service.zu_list_item(b, mandanten, users) for b in berichte]


async def _detail_antwort(session: AsyncSession, bericht: Fehlerbericht) -> FehlerberichtDetail:
    mandanten, users = await fehlerbericht_service.namen_laden(session, [bericht])
    return fehlerbericht_service.zu_detail(bericht, mandanten, users)


async def _hole(session: AsyncSession, bericht_id: uuid.UUID) -> Fehlerbericht:
    # RLS liefert fuer fremde Mandanten nichts -> 404 statt 403.
    bericht = await session.get(Fehlerbericht, bericht_id)
    if bericht is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fehlerbericht nicht gefunden")
    return bericht


# --- Nutzer-API ------------------------------------------------------------


@router.post("", response_model=FehlerberichtCreated, status_code=status.HTTP_201_CREATED)
async def create_fehlerbericht(
    request: Request,
    auth: AuthContext = Depends(require_roles("mandant_admin", "custom")),
    _recht: AuthContext = Depends(require_recht("fehlerberichte", "erstellen")),
    session: AsyncSession = Depends(get_db),
) -> FehlerberichtCreated:
    fehlerbericht_user_limiter.hit(str(auth.user_id))

    # Request statt Form(...)-Parameter: Starlette lehnt Textfelder > 1 MB sonst
    # schon beim Parsen mit 400 ab, die Spec verlangt fuer zu grossen Kontext 413.
    async with request.form(max_part_size=_PAYLOAD_PARSE_MAX_BYTES) as form:
        payload = form.get("payload")
        screenshot_original = form.get("screenshot_original")
        screenshot_annotiert = form.get("screenshot_annotiert")
        return await _lege_an(session, auth, payload, screenshot_original, screenshot_annotiert)


async def _lege_an(
    session: AsyncSession,
    auth: AuthContext,
    payload,
    screenshot_original,
    screenshot_annotiert,
) -> FehlerberichtCreated:
    if not isinstance(payload, str):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Feld payload fehlt")
    for datei in (screenshot_original, screenshot_annotiert):
        if datei is not None and not isinstance(datei, StarletteUploadFile):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Screenshot muss eine Datei sein")
    if len(payload.encode()) > fehlerbericht_service.KONTEXT_MAX_BYTES + 64 * 1024:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Payload zu groß")
    try:
        daten = FehlerberichtCreate.model_validate(json.loads(payload))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Ungültiger Payload: {exc}")
    if daten.art == "idee" and daten.schweregrad == "blockierend":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ideen können nicht „blockierend“ sein",
        )
    fehlerbericht_service.pruefe_kontext_groesse(daten.kontext)

    bilder: dict[str, tuple[bytes, str]] = {}
    for art, datei in (("original", screenshot_original), ("annotiert", screenshot_annotiert)):
        if datei is not None:
            bilder[art] = await fehlerbericht_service.lese_screenshot(datei)

    kontext = fehlerbericht_service.schwaerze(daten.kontext)
    bericht_id = uuid.uuid4()
    # Ideen haben keinen Fehlerkontext -> keine Duplikaterkennung.
    fingerprint = None if daten.art == "idee" else fehlerbericht_service.berechne_fingerprint(kontext, daten.route)
    duplikat_von_id = await fehlerbericht_service.finde_offenes_duplikat(
        session, mandant_id=auth.mandant_id, fingerprint=fingerprint
    )

    keys: dict[str, str] = {}
    try:
        for art, (data, content_type) in bilder.items():
            keys[art] = storage_service.new_fehlerbericht_screenshot_key(auth.mandant_id, bericht_id, art)
            await storage_service.upload_bytes(keys[art], data, content_type)
        bericht = Fehlerbericht(
            id=bericht_id,
            mandant_id=auth.mandant_id,
            user_id=auth.user_id,
            art=daten.art,
            titel=daten.titel,
            beschreibung=daten.beschreibung,
            erwartet=daten.erwartet,
            schritte=daten.schritte,
            schweregrad=daten.schweregrad,
            kontext=kontext,
            screenshot_original_key=keys.get("original"),
            screenshot_annotiert_key=keys.get("annotiert"),
            route=daten.route,
            app_version=daten.app_version,
            commit_sha=daten.commit_sha,
            fingerprint=fingerprint,
            duplikat_von_id=duplikat_von_id,
        )
        session.add(bericht)
        await session.flush()
    except Exception:
        await fehlerbericht_service.loesche_screenshots(list(keys.values()))
        raise
    return FehlerberichtCreated(id=bericht_id, duplikat_von_id=duplikat_von_id)


@router.get("", response_model=list[FehlerberichtListItem])
async def list_fehlerberichte(
    status_: FehlerberichtStatus | None = Query(default=None, alias="status"),
    schweregrad: FehlerberichtSchweregrad | None = None,
    art: FehlerberichtArt | None = None,
    seit: datetime | None = None,
    q: str | None = Query(default=None, max_length=200),
    mandant_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    auth: AuthContext = Depends(require_roles(*_ROLLEN)),
    _recht: AuthContext = Depends(require_recht("fehlerberichte", "sehen")),
    session: AsyncSession = Depends(get_db),
) -> list[FehlerberichtListItem]:
    stmt = _gefiltert(select(Fehlerbericht), status_=status_, schweregrad=schweregrad, art=art, seit=seit, q=q)
    # Der Mandantenfilter ist nur fuer super_admin relevant; alle anderen sind
    # per RLS ohnehin auf den eigenen Mandanten festgenagelt.
    if mandant_id is not None and ist_plattform_admin(auth):
        stmt = stmt.where(Fehlerbericht.mandant_id == mandant_id)
    stmt = stmt.order_by(Fehlerbericht.created_at.desc()).limit(limit).offset(offset)
    return await _liste_antwort(session, stmt)


@router.get("/zaehler", response_model=FehlerberichtZaehler)
async def zaehler_fehlerberichte(
    mandant_id: uuid.UUID | None = None,
    art: FehlerberichtArt | None = None,
    auth: AuthContext = Depends(require_roles(*_ROLLEN)),
    _recht: AuthContext = Depends(require_recht("fehlerberichte", "sehen")),
    session: AsyncSession = Depends(get_db),
) -> FehlerberichtZaehler:
    filter_mandant = mandant_id if ist_plattform_admin(auth) else None
    je_status = await fehlerbericht_service.zaehler_je_status(session, filter_mandant, art)
    return FehlerberichtZaehler(**je_status, gesamt=sum(je_status.values()))


@router.get("/{bericht_id}", response_model=FehlerberichtDetail)
async def get_fehlerbericht(
    bericht_id: uuid.UUID,
    _auth: AuthContext = Depends(require_roles(*_ROLLEN)),
    _recht: AuthContext = Depends(require_recht("fehlerberichte", "sehen")),
    session: AsyncSession = Depends(get_db),
) -> FehlerberichtDetail:
    return await _detail_antwort(session, await _hole(session, bericht_id))


@router.get("/{bericht_id}/ai-bundle", response_class=PlainTextResponse)
async def get_fehlerbericht_ai_bundle(
    bericht_id: uuid.UUID,
    _auth: AuthContext = Depends(require_roles(*_ROLLEN)),
    _recht: AuthContext = Depends(require_recht("fehlerberichte", "sehen")),
    session: AsyncSession = Depends(get_db),
) -> Response:
    bericht = await _hole(session, bericht_id)
    return PlainTextResponse(
        fehlerbericht_service.ai_bundle_markdown(bericht), media_type="text/markdown; charset=utf-8"
    )


@router.patch("/{bericht_id}", response_model=FehlerberichtDetail)
async def update_fehlerbericht(
    bericht_id: uuid.UUID,
    body: FehlerberichtUpdate,
    auth: AuthContext = Depends(require_roles(*_ROLLEN)),
    _recht: AuthContext = Depends(require_recht("fehlerberichte", "bearbeiten")),
    session: AsyncSession = Depends(get_db),
) -> FehlerberichtDetail:
    bericht = await _hole(session, bericht_id)
    daten = body.model_dump(exclude_unset=True)
    if bericht.art == "idee" and not ist_plattform_admin(auth) and daten:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ideen werden vom Betreiber freigegeben")
    if daten.get("duplikat_von_id") is not None:
        if daten["duplikat_von_id"] == bericht.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Bericht kann kein Duplikat von sich selbst sein"
            )
        await _hole(session, daten["duplikat_von_id"])
    fehlerbericht_service.wende_update_an(bericht, daten)
    await session.flush()
    await session.refresh(bericht)
    return await _detail_antwort(session, bericht)


@router.delete("/{bericht_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fehlerbericht(
    bericht_id: uuid.UUID,
    _auth: AuthContext = Depends(require_roles(*_ROLLEN)),
    _recht: AuthContext = Depends(require_recht("fehlerberichte", "loeschen")),
    session: AsyncSession = Depends(get_db),
) -> None:
    bericht = await _hole(session, bericht_id)
    keys = [bericht.screenshot_original_key, bericht.screenshot_annotiert_key]
    await session.delete(bericht)
    await session.flush()
    await fehlerbericht_service.loesche_screenshots(keys)


# --- Service-API (Claude, Bearer-Token statt JWT) --------------------------


async def _service_auth(request: Request) -> None:
    erwartet = get_settings().fehlerbericht_service_token_hash
    if not erwartet:
        # Ohne konfigurierten Hash soll die Service-API nicht einmal als
        # existierend erkennbar sein.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    ip = client_ip(request)
    fehlerbericht_service_ip_limiter.check(ip)
    kopf = request.headers.get("authorization", "")
    schema, _, token = kopf.partition(" ")
    ok = schema.lower() == "bearer" and bool(token) and hmac.compare_digest(
        hashlib.sha256(token.strip().encode()).hexdigest(), erwartet.strip().lower()
    )
    if not ok:
        fehlerbericht_service_ip_limiter.record_failure(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges Token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def _service_db(_: None = Depends(_service_auth)) -> AsyncIterator[AsyncSession]:
    # Von _service_auth abhaengig, damit vor erfolgreicher Authentifizierung
    # keine DB-Session geoeffnet wird.
    async with system_session() as session:
        yield session


async def _audit(
    session: AsyncSession, request: Request, *, bericht: Fehlerbericht | None = None, payload: dict | None = None
) -> None:
    await audit_service.log_action(
        session,
        aktion="fehlerbericht.service_zugriff",
        mandant_id=bericht.mandant_id if bericht else None,
        entity_type="fehlerbericht" if bericht else None,
        entity_id=bericht.id if bericht else None,
        payload={
            "methode": request.method,
            "pfad": request.url.path,
            "ip": client_ip(request),
            **(payload or {}),
        },
    )


@service_router.get("", response_model=list[FehlerberichtListItem])
async def service_list(
    request: Request,
    status_: FehlerberichtStatus | None = Query(default=None, alias="status"),
    schweregrad: FehlerberichtSchweregrad | None = None,
    art: FehlerberichtArt | None = None,
    seit: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(_service_db),
) -> list[FehlerberichtListItem]:
    stmt = _gefiltert(select(Fehlerbericht), status_=status_, schweregrad=schweregrad, art=art, seit=seit)
    stmt = stmt.order_by(Fehlerbericht.created_at.desc()).limit(limit)
    antwort = await _liste_antwort(session, stmt)
    await _audit(session, request, payload={"anzahl": len(antwort)})
    return antwort


@service_router.get("/{bericht_id}", response_model=FehlerberichtDetail)
async def service_detail(
    bericht_id: uuid.UUID, request: Request, session: AsyncSession = Depends(_service_db)
) -> FehlerberichtDetail:
    bericht = await _hole(session, bericht_id)
    await _audit(session, request, bericht=bericht)
    return await _detail_antwort(session, bericht)


@service_router.get("/{bericht_id}/ai-bundle", response_class=PlainTextResponse)
async def service_ai_bundle(
    bericht_id: uuid.UUID, request: Request, session: AsyncSession = Depends(_service_db)
) -> Response:
    bericht = await _hole(session, bericht_id)
    await _audit(session, request, bericht=bericht)
    return PlainTextResponse(
        fehlerbericht_service.ai_bundle_markdown(bericht), media_type="text/markdown; charset=utf-8"
    )


@service_router.get("/{bericht_id}/aehnliche", response_model=list[FehlerberichtListItem])
async def service_aehnliche(
    bericht_id: uuid.UUID, request: Request, session: AsyncSession = Depends(_service_db)
) -> list[FehlerberichtListItem]:
    bericht = await _hole(session, bericht_id)
    await _audit(session, request, bericht=bericht)
    if not bericht.fingerprint:
        return []
    stmt = (
        select(Fehlerbericht)
        .where(Fehlerbericht.fingerprint == bericht.fingerprint, Fehlerbericht.id != bericht.id)
        .order_by(Fehlerbericht.created_at.desc())
        .limit(50)
    )
    return await _liste_antwort(session, stmt)


@service_router.patch("/{bericht_id}", response_model=FehlerberichtDetail)
async def service_update(
    bericht_id: uuid.UUID,
    body: FehlerberichtServiceUpdate,
    request: Request,
    session: AsyncSession = Depends(_service_db),
) -> FehlerberichtDetail:
    bericht = await _hole(session, bericht_id)
    daten = body.model_dump(exclude_unset=True)
    if bericht.art == "idee":
        neu = daten.get("status")
        if neu in ("gesichtet", "abgelehnt", "duplikat", "neu"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Ideen werden vom Betreiber freigegeben bzw. abgelehnt"
            )
        if neu in ("in_arbeit", "behoben") and bericht.status not in ("gesichtet", "in_arbeit"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idee nicht freigegeben")
    fehlerbericht_service.wende_update_an(bericht, daten)
    await session.flush()
    await session.refresh(bericht)
    await _audit(session, request, bericht=bericht, payload={"felder": sorted(daten)})
    return await _detail_antwort(session, bericht)
