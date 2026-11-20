from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_recht, require_roles
from app.api.routes.auftraege import _require_auftrag
from app.api.routes.projekte import _require_projekt
from app.models.kunde import Kunde
from app.models.vor_ort_kontakt import VorOrtKontakt, VorOrtKontaktZuordnung
from app.models.vorgang import Vorgang
from app.schemas.vor_ort_kontakt import (
    VorOrtKontaktCreate,
    VorOrtKontaktOut,
    VorOrtKontaktUpdate,
    VorOrtKontaktZugeordnet,
    VorOrtRolle,
    VorOrtZuordnungCreate,
    VorOrtZuordnungUpdate,
)
from app.services import berechtigung_service, papierkorb_service, vor_ort_kontakt_service
from app.services.zuweisung_service import (
    erlaubte_kunde_ids,
    require_kunde_zugriff,
    require_vorgang_zugriff,
)

# Kein eigener Rechte-Bereich: Sichtbarkeit folgt dem Kunden bzw. dem Ziel (Vorgang/Auftrag/Projekt, inkl.
# Kundenbetreuung), Bearbeiten dem Recht auf das Ziel. Auftrag und Projekt nutzen den Bereich "projekte".
router = APIRouter(tags=["vor-ort-kontakte"])

_LESEN = (Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),)
_SCHREIBEN = (Depends(require_roles("mandant_admin", "custom")),)
_KONTAKT_NICHT_GEFUNDEN = "Kontakt nicht gefunden"


# --- Kontakte am Kunden ---------------------------------------------------------------------------


async def _kunde_pruefen(session: AsyncSession, auth: AuthContext, kunde_id: UUID, aktion: str) -> Kunde:
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None or kunde.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")
    await require_kunde_zugriff(session, auth, kunde_id, "Kunde nicht gefunden", aktion)
    return kunde


async def _kontakt_laden(session: AsyncSession, auth: AuthContext, kontakt_id: UUID, aktion: str) -> VorOrtKontakt:
    kontakt = await session.get(VorOrtKontakt, kontakt_id)
    if kontakt is None or kontakt.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_KONTAKT_NICHT_GEFUNDEN)
    await require_kunde_zugriff(session, auth, kontakt.kunde_id, _KONTAKT_NICHT_GEFUNDEN, aktion)
    return kontakt


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get(
    "/api/kunden/{kunde_id}/vor-ort-kontakte",
    response_model=list[VorOrtKontaktOut],
    dependencies=[*_LESEN, Depends(require_recht("kunden", "sehen"))],
)
async def kontakte_des_kunden(
    kunde_id: UUID,
    standort_id: UUID | None = Query(default=None),
    rolle: VorOrtRolle | None = Query(default=None),
    q: str | None = Query(default=None, description="Suche in Name, Telefon, Einheit"),
    mit_anonymisierten: bool = Query(default=True),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[VorOrtKontaktOut]:
    await _kunde_pruefen(session, auth, kunde_id, "sehen")
    stmt = select(VorOrtKontakt).where(VorOrtKontakt.kunde_id == kunde_id, VorOrtKontakt.geloescht_am.is_(None))
    if standort_id:
        stmt = stmt.where(VorOrtKontakt.standort_id == standort_id)
    if rolle:
        stmt = stmt.where(VorOrtKontakt.rolle == rolle)
    if not mit_anonymisierten:
        stmt = stmt.where(VorOrtKontakt.anonymisiert_am.is_(None))
    if q and q.strip():
        muster = _like(q.strip())
        stmt = stmt.where(
            or_(
                VorOrtKontakt.name.ilike(muster, escape="\\"),
                VorOrtKontakt.telefon.ilike(muster, escape="\\"),
                VorOrtKontakt.telefon2.ilike(muster, escape="\\"),
                VorOrtKontakt.einheit.ilike(muster, escape="\\"),
            )
        )
    stmt = stmt.order_by(VorOrtKontakt.anonymisiert_am.is_not(None), VorOrtKontakt.name, VorOrtKontakt.created_at)
    return await vor_ort_kontakt_service.kontakte_als_out(session, list((await session.execute(stmt)).scalars()))


@router.post(
    "/api/kunden/{kunde_id}/vor-ort-kontakte",
    response_model=VorOrtKontaktOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[*_SCHREIBEN, Depends(require_recht("kunden", "bearbeiten"))],
)
async def kontakt_anlegen(
    kunde_id: UUID,
    body: VorOrtKontaktCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorOrtKontaktOut:
    await _kunde_pruefen(session, auth, kunde_id, "bearbeiten")
    kontakt = await vor_ort_kontakt_service.kontakt_anlegen(
        session, mandant_id=auth.mandant_id, user_id=auth.user_id, kunde_id=kunde_id, body=body
    )
    [out] = await vor_ort_kontakt_service.kontakte_als_out(session, [kontakt])
    return out


@router.patch(
    "/api/vor-ort-kontakte/{kontakt_id}",
    response_model=VorOrtKontaktOut,
    dependencies=[*_SCHREIBEN, Depends(require_recht("kunden", "bearbeiten"))],
)
async def kontakt_aendern(
    kontakt_id: UUID,
    body: VorOrtKontaktUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorOrtKontaktOut:
    kontakt = await _kontakt_laden(session, auth, kontakt_id, "bearbeiten")
    if kontakt.anonymisiert_am is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Anonymisierte Kontakte sind nicht änderbar")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("standort_id") is not None:
        await vor_ort_kontakt_service.standort_pruefen(session, changes["standort_id"], kontakt.kunde_id)
    for feld, wert in changes.items():
        setattr(kontakt, feld, wert)
    if not kontakt.name and not kontakt.telefon:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Name oder Telefon angeben")
    await session.flush()
    await session.refresh(kontakt)
    [out] = await vor_ort_kontakt_service.kontakte_als_out(session, [kontakt])
    return out


@router.delete(
    "/api/vor-ort-kontakte/{kontakt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[*_SCHREIBEN, Depends(require_recht("kunden", "bearbeiten"))],
)
async def kontakt_loeschen(
    kontakt_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await _kontakt_laden(session, auth, kontakt_id, "bearbeiten")
    await papierkorb_service.soft_delete(
        session, entity_typ="vor_ort_kontakt", entity_id=kontakt_id, actor_user_id=auth.user_id
    )


@router.post(
    "/api/vor-ort-kontakte/{kontakt_id}/anonymisieren",
    response_model=VorOrtKontaktOut,
    dependencies=[*_SCHREIBEN, Depends(require_recht("kunden", "bearbeiten"))],
)
async def kontakt_anonymisieren(
    kontakt_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorOrtKontaktOut:
    kontakt = await _kontakt_laden(session, auth, kontakt_id, "bearbeiten")
    if kontakt.anonymisiert_am is None:
        await vor_ort_kontakt_service.anonymisieren_mit_protokoll(
            session, kontakt, actor_user_id=auth.user_id, grund="manuell"
        )
        await session.refresh(kontakt)
    [out] = await vor_ort_kontakt_service.kontakte_als_out(session, [kontakt])
    return out


# --- Kontakte an Vorgang / Auftrag / Projekt ------------------------------------------------------


async def _projekt_laden(session: AsyncSession, auth: AuthContext, projekt_id: UUID):
    projekt = await _require_projekt(session, projekt_id)
    # Seit dem Auftraggeber am Projekt gilt fuer Eingeschraenkte dessen Kundenscope; Projekte ohne Kunde
    # bleiben sichtbar (kein Kundenbezug, den man schuetzen muesste), wie bei Auftraegen.
    if projekt.kunde_id is not None:
        erlaubt = await erlaubte_kunde_ids(session, auth)
        if erlaubt is not None and projekt.kunde_id not in erlaubt:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projekt nicht gefunden")
    return projekt


async def _vorgang_laden(session: AsyncSession, auth: AuthContext, vorgang_id: UUID, aktion: str) -> Vorgang:
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None or vorgang.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
    await require_vorgang_zugriff(session, auth, vorgang, aktion)
    return vorgang


async def _ziel_laden(session: AsyncSession, auth: AuthContext, typ: str, ziel_id: UUID, aktion: str):
    if typ == "vorgang":
        return await _vorgang_laden(session, auth, ziel_id, aktion)
    if typ == "auftrag":
        return await _require_auftrag(session, auth, ziel_id)
    return await _projekt_laden(session, auth, ziel_id)


async def _bearbeiten_recht(session: AsyncSession, auth: AuthContext, typ: str) -> None:
    bereich = "vorgaenge" if typ == "vorgang" else "projekte"
    if not await berechtigung_service.hat_recht(session, auth, bereich, "bearbeiten"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Keine Berechtigung für diese Aktion")


async def _liste(session: AsyncSession, typ: str, ziel) -> list[VorOrtKontaktZugeordnet]:
    return await vor_ort_kontakt_service.kontakte_fuer_ziel(session, **{typ: ziel})


@router.get(
    "/api/vorgaenge/{vorgang_id}/vor-ort-kontakte",
    response_model=list[VorOrtKontaktZugeordnet],
    dependencies=[*_LESEN, Depends(require_recht("vorgaenge", "sehen"))],
)
async def kontakte_des_vorgangs(
    vorgang_id: UUID, auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> list[VorOrtKontaktZugeordnet]:
    return await _liste(session, "vorgang", await _vorgang_laden(session, auth, vorgang_id, "sehen"))


@router.get(
    "/api/auftraege/{auftrag_id}/vor-ort-kontakte",
    response_model=list[VorOrtKontaktZugeordnet],
    dependencies=[*_LESEN, Depends(require_recht("projekte", "sehen"))],
)
async def kontakte_des_auftrags(
    auftrag_id: UUID, auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> list[VorOrtKontaktZugeordnet]:
    return await _liste(session, "auftrag", await _require_auftrag(session, auth, auftrag_id))


@router.get(
    "/api/projekte/{projekt_id}/vor-ort-kontakte",
    response_model=list[VorOrtKontaktZugeordnet],
    dependencies=[*_LESEN, Depends(require_recht("projekte", "sehen"))],
)
async def kontakte_des_projekts(
    projekt_id: UUID, auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> list[VorOrtKontaktZugeordnet]:
    return await _liste(session, "projekt", await _projekt_laden(session, auth, projekt_id))


async def _zuordnen(
    session: AsyncSession, auth: AuthContext, ziel, body: VorOrtZuordnungCreate
) -> VorOrtKontaktZugeordnet:
    return await vor_ort_kontakt_service.zuordnen(
        session, mandant_id=auth.mandant_id, user_id=auth.user_id, ziel=ziel, body=body
    )


@router.post(
    "/api/vorgaenge/{vorgang_id}/vor-ort-kontakte",
    response_model=VorOrtKontaktZugeordnet,
    status_code=status.HTTP_201_CREATED,
    dependencies=[*_SCHREIBEN, Depends(require_recht("vorgaenge", "bearbeiten"))],
)
async def kontakt_an_vorgang(
    vorgang_id: UUID,
    body: VorOrtZuordnungCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorOrtKontaktZugeordnet:
    return await _zuordnen(session, auth, await _vorgang_laden(session, auth, vorgang_id, "bearbeiten"), body)


@router.post(
    "/api/auftraege/{auftrag_id}/vor-ort-kontakte",
    response_model=VorOrtKontaktZugeordnet,
    status_code=status.HTTP_201_CREATED,
    dependencies=[*_SCHREIBEN, Depends(require_recht("projekte", "bearbeiten"))],
)
async def kontakt_an_auftrag(
    auftrag_id: UUID,
    body: VorOrtZuordnungCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorOrtKontaktZugeordnet:
    return await _zuordnen(session, auth, await _require_auftrag(session, auth, auftrag_id), body)


@router.post(
    "/api/projekte/{projekt_id}/vor-ort-kontakte",
    response_model=VorOrtKontaktZugeordnet,
    status_code=status.HTTP_201_CREATED,
    dependencies=[*_SCHREIBEN, Depends(require_recht("projekte", "bearbeiten"))],
)
async def kontakt_an_projekt(
    projekt_id: UUID,
    body: VorOrtZuordnungCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorOrtKontaktZugeordnet:
    return await _zuordnen(session, auth, await _projekt_laden(session, auth, projekt_id), body)


async def _zuordnung_mit_ziel(session: AsyncSession, auth: AuthContext, zuordnung_id: UUID):
    zuordnung = await session.get(VorOrtKontaktZuordnung, zuordnung_id)
    if zuordnung is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zuordnung nicht gefunden")
    typ = next(t for t in ("vorgang", "auftrag", "projekt") if getattr(zuordnung, f"{t}_id") is not None)
    await _bearbeiten_recht(session, auth, typ)
    try:
        await _ziel_laden(session, auth, typ, getattr(zuordnung, f"{typ}_id"), "bearbeiten")
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zuordnung nicht gefunden") from exc
        raise
    return zuordnung


@router.patch(
    "/api/vor-ort-kontakt-zuordnungen/{zuordnung_id}",
    response_model=VorOrtKontaktZugeordnet,
    dependencies=_SCHREIBEN,
)
async def zuordnung_aendern(
    zuordnung_id: UUID,
    body: VorOrtZuordnungUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorOrtKontaktZugeordnet:
    zuordnung = await _zuordnung_mit_ziel(session, auth, zuordnung_id)
    return await vor_ort_kontakt_service.hauptkontakt_setzen(session, zuordnung, body.ist_hauptkontakt)


@router.delete(
    "/api/vor-ort-kontakt-zuordnungen/{zuordnung_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=_SCHREIBEN,
)
async def zuordnung_entfernen(
    zuordnung_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    zuordnung = await _zuordnung_mit_ziel(session, auth, zuordnung_id)
    await session.delete(zuordnung)
    await session.flush()
