"""Organigramm: Lesen mit Scope/DSGVO, Schreiben mit Eskalationsschutz, Zyklenschutz
und Audit (docs/konzepte/ORGANIGRAMM.md, Schritt 3). Rechte-Aufloesung ausschliesslich
ueber die Engine (berechtigung_service), Vergabe-Pruefungen in eskalation_service."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.account_typ import AccountTyp
from app.models.organigramm import (
    OrgEinheit,
    Position,
    PositionBesetzung,
    PositionRecht,
    UserRecht,
)
from app.models.user import User
from app.schemas.organigramm import (
    BesetzungCreate,
    BesetzungErgebnis,
    BesetzungRead,
    BesetzungUpdate,
    EffektivesRechtRead,
    EffektivRead,
    OrgEinheitCreate,
    OrgEinheitRead,
    OrgEinheitUpdate,
    PositionCreate,
    PositionDetailRead,
    PositionRead,
    PositionUpdate,
    RechtOverrideIn,
    RechtOverrideRead,
)
from app.services import berechtigung_service as bs
from app.services import eskalation_service as esk
from app.services import organigramm_service as org
from app.services.audit_service import log_aenderung
from app.services.zuweisung_service import zuweisbare_user_ids

LESEN = ("super_admin", "mandant_admin", "custom", "loesch_ansicht", "loesch_operativ")
SCHREIBEN = ("super_admin", "mandant_admin", "custom")

router = APIRouter(prefix="/api/organigramm", tags=["organigramm"])

_SEHEN = (("organigramm", "sehen"),)
_PERSONEN_SEHEN = (("mitarbeiterverwaltung", "sehen"),)


def _nicht_gefunden(was: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{was} nicht gefunden")


def _konflikt(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _mandant(auth: AuthContext) -> UUID:
    if auth.mandant_id is None:
        raise esk.verboten("Nur im Mandantenkontext verfügbar")
    return auth.mandant_id


async def _position(session: AsyncSession, auth: AuthContext, position_id: UUID) -> Position:
    # Expliziter Mandantenfilter zusaetzlich zur RLS (super_admin-/Impersonations-Sessions).
    position = (
        await session.execute(
            select(Position).where(Position.id == position_id, Position.mandant_id == _mandant(auth))
        )
    ).scalar_one_or_none()
    if position is None:
        raise _nicht_gefunden("Position")
    return position


async def _einheit(session: AsyncSession, auth: AuthContext, einheit_id: UUID) -> OrgEinheit:
    einheit = (
        await session.execute(
            select(OrgEinheit).where(OrgEinheit.id == einheit_id, OrgEinheit.mandant_id == _mandant(auth))
        )
    ).scalar_one_or_none()
    if einheit is None:
        raise _nicht_gefunden("Organisationseinheit")
    return einheit


async def _account_typ(session: AsyncSession, auth: AuthContext, typ_id: UUID) -> AccountTyp:
    typ = await session.get(AccountTyp, typ_id)
    if typ is None or typ.mandant_id != auth.mandant_id:
        raise _nicht_gefunden("Account-Typ")
    return typ


async def _schreib_akteur(session: AsyncSession, auth: AuthContext) -> esk.Akteur:
    _mandant(auth)
    return await esk.akteur_laden(session, auth)


# --- Lesen ------------------------------------------------------------------


async def _namens_filter(session: AsyncSession, akteur: esk.Akteur):
    """DSGVO: Namen nur mit mitarbeiterverwaltung.sehen und nur fuer Nutzer in dessen Scope."""
    if not akteur.hat(*_PERSONEN_SEHEN[0]):
        return lambda user_id: False
    erlaubt = await esk.user_ids_im_scope(session, akteur, _PERSONEN_SEHEN)
    return (lambda user_id: True) if erlaubt is None else (lambda user_id: user_id in erlaubt)


async def _besetzung_reads(
    session: AsyncSession, besetzungen: list[PositionBesetzung], darf
) -> dict[UUID, BesetzungRead]:
    ids = {b.user_id for b in besetzungen if darf(b.user_id)}
    namen: dict[UUID, str] = {}
    if ids:
        namen = {
            row[0]: row[1] for row in await session.execute(select(User.id, User.name).where(User.id.in_(ids)))
        }
    ergebnis: dict[UUID, BesetzungRead] = {}
    for b in besetzungen:
        if darf(b.user_id):
            ergebnis[b.id] = BesetzungRead(
                id=b.id,
                user_id=b.user_id,
                name=namen.get(b.user_id),
                art=b.art,
                gueltig_von=b.gueltig_von,
                gueltig_bis=b.gueltig_bis,
            )
        else:
            # user_id bleibt ungesetzt und faellt per exclude_unset aus der Antwort.
            ergebnis[b.id] = BesetzungRead(
                id=b.id, name=None, art=b.art, gueltig_von=b.gueltig_von, gueltig_bis=b.gueltig_bis
            )
    return ergebnis


async def _alle_positionen(session: AsyncSession, mandant_id: UUID) -> dict[UUID, Position]:
    zeilen = await session.execute(select(Position).where(Position.mandant_id == mandant_id))
    return {p.id: p for p in zeilen.scalars()}


async def _position_read(
    session: AsyncSession,
    position: Position,
    aktive: list[PositionBesetzung],
    reads: dict[UUID, BesetzungRead],
    einheiten: dict[UUID, OrgEinheit],
    typen: dict[UUID, AccountTyp],
    *,
    klasse=PositionRead,
    **extra,
):
    einheit = einheiten.get(position.org_einheit_id) if position.org_einheit_id else None
    typ = typen.get(position.account_typ_id) if position.account_typ_id else None
    return klasse(
        id=position.id,
        parent_id=position.parent_id,
        titel=position.titel,
        typ=position.typ,
        kontext=False,
        ist_ausser_linie=position.typ == "stabsstelle",
        status=org.status_von(position, len(aktive)),
        ebene=position.ebene,
        org_einheit={"id": einheit.id, "name": einheit.name, "typ": einheit.typ} if einheit else None,
        account_typ={"id": typ.id, "name": typ.name} if typ else None,
        geplant=position.geplant,
        soll_besetzung=position.soll_besetzung,
        ist_besetzung=sum(1 for b in aktive if b.art == "regulaer"),
        gueltig_ab=position.gueltig_ab,
        gueltig_bis=position.gueltig_bis,
        archiviert_am=position.archiviert_am,
        reihenfolge=position.reihenfolge,
        besetzungen=[reads[b.id] for b in aktive],
        **extra,
    )


async def _stammdaten(session: AsyncSession, mandant_id: UUID):
    einheiten = {
        e.id: e
        for e in (await session.execute(select(OrgEinheit).where(OrgEinheit.mandant_id == mandant_id))).scalars()
    }
    typen = {
        t.id: t
        for t in (await session.execute(select(AccountTyp).where(AccountTyp.mandant_id == mandant_id))).scalars()
    }
    return einheiten, typen


@router.get(
    "/positionen",
    response_model=list[PositionRead],
    response_model_exclude_unset=True,
    dependencies=[Depends(require_roles(*LESEN))],
)
async def list_positionen(
    archivierte: bool = False,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[PositionRead]:
    mandant_id = _mandant(auth)
    akteur = await esk.akteur_laden(session, auth)
    esk.recht_pflicht(akteur, "organigramm", "sehen")
    alle = await _alle_positionen(session, mandant_id)
    scope = await esk.position_ids_im_scope(session, akteur, _SEHEN)

    sichtbar: set[UUID] = set()
    for pid, p in alle.items():
        if p.archiviert_am is not None and not archivierte:
            continue
        if scope is None or pid in scope or (p.archiviert_am is not None and p.parent_id in scope):
            sichtbar.add(pid)

    kontext: set[UUID] = set()
    for pid in sichtbar:
        aktuell = alle[pid].parent_id
        while aktuell is not None and aktuell in alle and aktuell not in sichtbar and aktuell not in kontext:
            kontext.add(aktuell)
            aktuell = alle[aktuell].parent_id

    stichtag = org.jetzt()
    aktive_je_position = await org.aktive_besetzungen(session, mandant_id, stichtag)
    darf = await _namens_filter(session, akteur)
    reads = await _besetzung_reads(
        session, [b for pid in sichtbar for b in aktive_je_position.get(pid, [])], darf
    )
    einheiten, typen = await _stammdaten(session, mandant_id)

    ergebnis: list[PositionRead] = []
    for p in sorted(alle.values(), key=lambda x: (x.reihenfolge, x.titel)):
        if p.id in sichtbar:
            ergebnis.append(
                await _position_read(session, p, aktive_je_position.get(p.id, []), reads, einheiten, typen)
            )
        elif p.id in kontext:
            ergebnis.append(PositionRead(id=p.id, parent_id=p.parent_id, titel=p.titel, typ=p.typ, kontext=True))
    return ergebnis


@router.get(
    "/positionen/{position_id}",
    response_model=PositionDetailRead,
    response_model_exclude_unset=True,
    dependencies=[Depends(require_roles(*LESEN))],
)
async def get_position(
    position_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> PositionDetailRead:
    mandant_id = _mandant(auth)
    akteur = await esk.akteur_laden(session, auth)
    esk.recht_pflicht(akteur, "organigramm", "sehen")
    position = await _position(session, auth, position_id)
    scope = await esk.position_ids_im_scope(session, akteur, _SEHEN)
    if scope is not None and position.id not in scope:
        raise esk.verboten("Die Position liegt außerhalb Ihres Verantwortungsbereichs")

    stichtag = org.jetzt()
    aktive = (await org.aktive_besetzungen(session, mandant_id, stichtag, position.id)).get(position.id, [])
    historie = list(
        (
            await session.execute(
                select(PositionBesetzung)
                .where(PositionBesetzung.position_id == position.id)
                .order_by(PositionBesetzung.gueltig_von.desc())
            )
        ).scalars()
    )
    darf = await _namens_filter(session, akteur)
    reads = await _besetzung_reads(session, historie, darf)
    einheiten, typen = await _stammdaten(session, mandant_id)
    rechte, diff, overrides = await org.position_effektiv(session, position)
    kinder = await session.scalar(
        select(func.count()).select_from(Position).where(
            Position.parent_id == position.id, Position.archiviert_am.is_(None)
        )
    )
    return await _position_read(
        session,
        position,
        aktive,
        reads,
        einheiten,
        typen,
        klasse=PositionDetailRead,
        alle_besetzungen=[reads[b.id] for b in historie],
        overrides=overrides,
        effektive_rechte=rechte,
        diff_zur_vorlage=diff,
        unterpositionen=kinder or 0,
    )


@router.get(
    "/org-einheiten",
    response_model=list[OrgEinheitRead],
    dependencies=[Depends(require_roles(*LESEN))],
)
async def list_org_einheiten(
    archivierte: bool = False,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[OrgEinheitRead]:
    akteur = await esk.akteur_laden(session, auth)
    esk.recht_pflicht(akteur, "organigramm", "sehen")
    stmt = select(OrgEinheit).where(OrgEinheit.mandant_id == _mandant(auth))
    if not archivierte:
        stmt = stmt.where(OrgEinheit.archiviert_am.is_(None))
    return [
        OrgEinheitRead.model_validate(e, from_attributes=True)
        for e in (await session.execute(stmt.order_by(OrgEinheit.name))).scalars()
    ]


@router.get("/effektiv", response_model=EffektivRead, dependencies=[Depends(require_roles(*LESEN))])
async def get_effektiv(
    user_id: UUID | None = Query(default=None),
    position_id: UUID | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> EffektivRead:
    """„Anzeigen als …“: effektive Rechte eines Nutzers bzw. einer Position."""
    if (user_id is None) == (position_id is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Genau eines von user_id oder position_id angeben",
        )
    _mandant(auth)
    akteur = await esk.akteur_laden(session, auth)
    esk.recht_pflicht(akteur, "organigramm", "sehen")

    if position_id is not None:
        position = await _position(session, auth, position_id)
        scope = await esk.position_ids_im_scope(session, akteur, _SEHEN)
        if scope is not None and position.id not in scope:
            raise esk.verboten("Die Position liegt außerhalb Ihres Verantwortungsbereichs")
        rechte, _, _ = await org.position_effektiv(session, position)
        return EffektivRead(
            position_id=position.id, rechte=[EffektivesRechtRead(**r) for r in rechte]
        )

    esk.recht_pflicht(akteur, *_PERSONEN_SEHEN[0])
    ziel = await session.get(User, user_id)
    if ziel is None or ziel.mandant_id != auth.mandant_id:
        raise _nicht_gefunden("Nutzer")
    await esk.user_im_scope_pruefen(session, akteur, _PERSONEN_SEHEN, ziel.id)
    eff = await bs.effektive_rechte(session, user_id=ziel.id, rolle=ziel.role)
    return EffektivRead(
        user_id=ziel.id,
        rolle=ziel.role,
        alle_rechte=eff.alle_rechte,
        rechte=[
            EffektivesRechtRead(bereich=r.bereich, aktion=r.aktion, scope=r.scope, herkunft=list(r.herkunft))
            for _, r in sorted(eff.rechte.items())
        ],
        verweigert=[
            {"bereich": b, "aktion": a, "herkunft": h} for (b, a), h in sorted(eff.verweigert.items())
        ],
    )


@router.get(
    "/users/{user_id}/rechte",
    response_model=list[RechtOverrideRead],
    dependencies=[Depends(require_roles(*SCHREIBEN))],
)
async def get_user_rechte(
    user_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[RechtOverrideRead]:
    akteur = await _schreib_akteur(session, auth)
    esk.rechte_verwalten_pflicht(akteur)
    ziel = await session.get(User, user_id)
    if ziel is None or ziel.mandant_id != auth.mandant_id:
        raise _nicht_gefunden("Nutzer")
    await esk.user_im_scope_pruefen(session, akteur, esk.RECHTE_VERWALTEN, ziel.id)
    zeilen = (await session.execute(select(UserRecht).where(UserRecht.user_id == ziel.id))).scalars()
    return [RechtOverrideRead(**e) for e in org.overrides_snapshot(zeilen)]


# --- Positionen schreiben ---------------------------------------------------


async def _einheit_pruefen(session: AsyncSession, auth: AuthContext, einheit_id: UUID) -> None:
    einheit = await _einheit(session, auth, einheit_id)
    if einheit.archiviert_am is not None:
        raise _konflikt("Die Organisationseinheit ist archiviert")


def _unter_archiviert_pruefen(parent: Position) -> None:
    if parent.archiviert_am is not None:
        raise _konflikt("Unter einer archivierten Position kann nichts angelegt oder eingehängt werden")


@router.post(
    "/positionen",
    response_model=PositionRead,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(*SCHREIBEN))],
)
async def create_position(
    body: PositionCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> PositionRead:
    mandant_id = _mandant(auth)
    akteur = await _schreib_akteur(session, auth)
    esk.recht_pflicht(akteur, "organigramm", "erstellen")
    await org.baum_sperren(session, mandant_id)
    parent = await _position(session, auth, body.parent_id)
    _unter_archiviert_pruefen(parent)
    await esk.position_im_scope_pruefen(session, akteur, (("organigramm", "erstellen"),), [parent.id])
    if body.org_einheit_id is not None:
        await _einheit_pruefen(session, auth, body.org_einheit_id)
    if body.account_typ_id is not None:
        await _account_typ(session, auth, body.account_typ_id)
        esk.rechte_verwalten_pflicht(akteur)
        esk.mehr_rechte_pruefen(akteur, await esk.typ_rechte_map(session, body.account_typ_id))

    position = Position(
        mandant_id=mandant_id,
        erstellt_von=auth.user_id,
        **body.model_dump(),
    )
    session.add(position)
    await session.flush()
    await log_aenderung(
        session,
        aktion="position_erstellt",
        mandant_id=mandant_id,
        actor_user_id=auth.user_id,
        entity_type="position",
        entity_id=position.id,
        vorher=None,
        nachher=org.position_snapshot(position),
    )
    einheiten, typen = await _stammdaten(session, mandant_id)
    return await _position_read(session, position, [], {}, einheiten, typen)


@router.patch(
    "/positionen/{position_id}",
    response_model=PositionRead,
    response_model_exclude_unset=True,
    dependencies=[Depends(require_roles(*SCHREIBEN))],
)
async def update_position(
    position_id: UUID,
    body: PositionUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> PositionRead:
    mandant_id = _mandant(auth)
    akteur = await _schreib_akteur(session, auth)
    esk.recht_pflicht(akteur, "organigramm", "bearbeiten")
    await org.baum_sperren(session, mandant_id)
    position = await _position(session, auth, position_id)
    bearbeiten = (("organigramm", "bearbeiten"),)
    await esk.position_im_scope_pruefen(session, akteur, bearbeiten, [position.id])
    if position.archiviert_am is not None:
        raise _konflikt("Archivierte Positionen können nicht bearbeitet werden")

    aenderungen = body.model_dump(exclude_unset=True)
    for pflicht in ("titel", "typ", "geplant", "soll_besetzung", "reihenfolge"):
        if pflicht in aenderungen and aenderungen[pflicht] is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{pflicht} darf nicht leer sein"
            )
    ist_wurzel = position.parent_id is None
    vorher = org.position_snapshot(position)

    if "parent_id" in aenderungen and aenderungen["parent_id"] != position.parent_id:
        if ist_wurzel:
            raise _konflikt("Die Wurzel kann nicht umgehängt werden")
        neuer_parent_id = aenderungen["parent_id"]
        if neuer_parent_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Eine Position braucht eine übergeordnete Position",
            )
        neuer_parent = await _position(session, auth, neuer_parent_id)
        _unter_archiviert_pruefen(neuer_parent)
        await esk.position_im_scope_pruefen(session, akteur, bearbeiten, [neuer_parent.id])
        if position.id in await org.pfad_zur_wurzel(session, "positionen", mandant_id, neuer_parent.id):
            raise _konflikt("Eine Position kann nicht unter sich selbst oder ihre Unterpositionen gehängt werden")
    elif "parent_id" in aenderungen and ist_wurzel and aenderungen["parent_id"] is not None:
        raise _konflikt("Die Wurzel kann nicht umgehängt werden")
    if ist_wurzel and aenderungen.get("typ", "linie") != "linie":
        raise _konflikt("Die Wurzel muss eine Linienposition bleiben")

    if aenderungen.get("org_einheit_id") is not None:
        await _einheit_pruefen(session, auth, aenderungen["org_einheit_id"])

    typ_wechsel = "account_typ_id" in aenderungen and aenderungen["account_typ_id"] != position.account_typ_id
    if typ_wechsel:
        esk.rechte_verwalten_pflicht(akteur)
        await esk.position_im_scope_pruefen(session, akteur, esk.RECHTE_VERWALTEN, [position.id])
        if aenderungen["account_typ_id"] is not None:
            await _account_typ(session, auth, aenderungen["account_typ_id"])
        overrides = [
            (o.bereich, o.aktion, o.wirkung, o.scope)
            for o in (
                await session.execute(select(PositionRecht).where(PositionRecht.position_id == position.id))
            ).scalars()
        ]
        alt = await esk.position_rechte_map(session, position.account_typ_id, overrides)
        neu = await esk.position_rechte_map(session, aenderungen["account_typ_id"], overrides)
        esk.mehr_rechte_pruefen(akteur, neu, alt)

    endgueltig_ab = aenderungen.get("gueltig_ab", position.gueltig_ab)
    endgueltig_bis = aenderungen.get("gueltig_bis", position.gueltig_bis)
    if endgueltig_ab and endgueltig_bis and endgueltig_bis < endgueltig_ab:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="gueltig_bis darf nicht vor gueltig_ab liegen"
        )

    async with esk.verwaltung_bleibt_erhalten(session, mandant_id):
        for feld, wert in aenderungen.items():
            setattr(position, feld, wert)
        await session.flush()
        bs.cache_leeren(session)
    await session.refresh(position)

    nachher = org.position_snapshot(position)
    geaendert = {k for k in nachher if nachher[k] != vorher[k]}
    if geaendert:
        await log_aenderung(
            session,
            aktion="position_geaendert",
            mandant_id=mandant_id,
            actor_user_id=auth.user_id,
            entity_type="position",
            entity_id=position.id,
            vorher={k: vorher[k] for k in geaendert},
            nachher={k: nachher[k] for k in geaendert},
        )
    einheiten, typen = await _stammdaten(session, mandant_id)
    aktive = (await org.aktive_besetzungen(session, mandant_id, org.jetzt(), position.id)).get(position.id, [])
    darf = await _namens_filter(session, akteur)
    reads = await _besetzung_reads(session, aktive, darf)
    return await _position_read(session, position, aktive, reads, einheiten, typen)


@router.post(
    "/positionen/{position_id}/duplizieren",
    response_model=PositionRead,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(*SCHREIBEN))],
)
async def duplicate_position(
    position_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> PositionRead:
    """Kopie ohne Besetzungen, aber mit Typ und Overrides (Vorlage fuer Platzhalter)."""
    mandant_id = _mandant(auth)
    akteur = await _schreib_akteur(session, auth)
    esk.recht_pflicht(akteur, "organigramm", "erstellen")
    await org.baum_sperren(session, mandant_id)
    quelle = await _position(session, auth, position_id)
    if quelle.parent_id is None:
        raise _konflikt("Die Wurzel kann nicht dupliziert werden")
    parent = await _position(session, auth, quelle.parent_id)
    _unter_archiviert_pruefen(parent)
    await esk.position_im_scope_pruefen(session, akteur, (("organigramm", "erstellen"),), [parent.id])

    overrides = list(
        (await session.execute(select(PositionRecht).where(PositionRecht.position_id == quelle.id))).scalars()
    )
    rechte_map = await esk.position_rechte_map(
        session, quelle.account_typ_id, [(o.bereich, o.aktion, o.wirkung, o.scope) for o in overrides]
    )
    if rechte_map or overrides:
        esk.rechte_verwalten_pflicht(akteur)
        esk.mehr_rechte_pruefen(akteur, rechte_map)

    kopie = Position(
        mandant_id=mandant_id,
        erstellt_von=auth.user_id,
        parent_id=quelle.parent_id,
        typ=quelle.typ,
        titel=f"{quelle.titel} (Kopie)",
        ebene=quelle.ebene,
        org_einheit_id=quelle.org_einheit_id,
        account_typ_id=quelle.account_typ_id,
        geplant=quelle.geplant,
        soll_besetzung=quelle.soll_besetzung,
        gueltig_ab=quelle.gueltig_ab,
        gueltig_bis=quelle.gueltig_bis,
        reihenfolge=quelle.reihenfolge + 1,
    )
    session.add(kopie)
    await session.flush()
    for o in overrides:
        session.add(
            PositionRecht(
                mandant_id=mandant_id,
                position_id=kopie.id,
                bereich=o.bereich,
                aktion=o.aktion,
                wirkung=o.wirkung,
                scope=o.scope,
            )
        )
    await session.flush()
    await log_aenderung(
        session,
        aktion="position_dupliziert",
        mandant_id=mandant_id,
        actor_user_id=auth.user_id,
        entity_type="position",
        entity_id=kopie.id,
        vorher={"quelle_id": quelle.id},
        nachher={**org.position_snapshot(kopie), "overrides": org.overrides_snapshot(overrides)},
    )
    einheiten, typen = await _stammdaten(session, mandant_id)
    return await _position_read(session, kopie, [], {}, einheiten, typen)


async def _loeschen_vorpruefung(
    session: AsyncSession, auth: AuthContext, position: Position, akteur: esk.Akteur
) -> None:
    await esk.position_im_scope_pruefen(session, akteur, (("organigramm", "loeschen"),), [position.id])
    if position.parent_id is None:
        raise _konflikt("Die Wurzel kann weder archiviert noch gelöscht werden")


@router.post(
    "/positionen/{position_id}/archivieren",
    response_model=PositionRead,
    response_model_exclude_unset=True,
    dependencies=[Depends(require_roles(*SCHREIBEN))],
)
async def archive_position(
    position_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> PositionRead:
    mandant_id = _mandant(auth)
    akteur = await _schreib_akteur(session, auth)
    esk.recht_pflicht(akteur, "organigramm", "loeschen")
    await org.baum_sperren(session, mandant_id)
    position = await _position(session, auth, position_id)
    await _loeschen_vorpruefung(session, auth, position, akteur)
    if position.archiviert_am is not None:
        raise _konflikt("Die Position ist bereits archiviert")
    kinder = await session.scalar(
        select(func.count()).select_from(Position).where(
            Position.parent_id == position.id, Position.archiviert_am.is_(None)
        )
    )
    if kinder:
        raise _konflikt(
            f"Die Position hat noch {kinder} Unterposition(en) – diese zuerst archivieren oder umhängen"
        )
    aktive = (await org.aktive_besetzungen(session, mandant_id, org.jetzt(), position.id)).get(position.id, [])
    bevorstehend = await session.scalar(
        select(func.count()).select_from(PositionBesetzung).where(
            PositionBesetzung.position_id == position.id,
            PositionBesetzung.gueltig_bis.is_(None),
        )
    )
    if aktive or bevorstehend:
        raise _konflikt("Die Position ist noch besetzt – Besetzungen zuerst beenden")

    vorher = org.position_snapshot(position)
    async with esk.verwaltung_bleibt_erhalten(session, mandant_id):
        position.archiviert_am = org.jetzt()
        await session.flush()
        bs.cache_leeren(session)
    await log_aenderung(
        session,
        aktion="position_archiviert",
        mandant_id=mandant_id,
        actor_user_id=auth.user_id,
        entity_type="position",
        entity_id=position.id,
        vorher=vorher,
        nachher=org.position_snapshot(position),
    )
    einheiten, typen = await _stammdaten(session, mandant_id)
    return await _position_read(session, position, [], {}, einheiten, typen)


@router.delete(
    "/positionen/{position_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(*SCHREIBEN))],
)
async def delete_position(
    position_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    mandant_id = _mandant(auth)
    akteur = await _schreib_akteur(session, auth)
    esk.recht_pflicht(akteur, "organigramm", "loeschen")
    await org.baum_sperren(session, mandant_id)
    position = await _position(session, auth, position_id)
    await _loeschen_vorpruefung(session, auth, position, akteur)
    kinder = await session.scalar(
        select(func.count()).select_from(Position).where(Position.parent_id == position.id)
    )
    if kinder:
        raise _konflikt("Die Position hat Unterpositionen und kann nicht gelöscht werden")
    besetzungen = await session.scalar(
        select(func.count()).select_from(PositionBesetzung).where(PositionBesetzung.position_id == position.id)
    )
    if besetzungen:
        raise _konflikt("Die Position war bereits besetzt und kann nur archiviert, nicht gelöscht werden")

    vorher = org.position_snapshot(position)
    overrides = org.overrides_snapshot(
        (await session.execute(select(PositionRecht).where(PositionRecht.position_id == position.id))).scalars()
    )
    await session.delete(position)
    await session.flush()
    await log_aenderung(
        session,
        aktion="position_geloescht",
        mandant_id=mandant_id,
        actor_user_id=auth.user_id,
        entity_type="position",
        entity_id=position_id,
        vorher={**vorher, "overrides": overrides},
        nachher=None,
    )


# --- Besetzungen ---------------------------------------------------------------


def _aware(wert: datetime | None) -> datetime | None:
    if wert is not None and wert.tzinfo is None:
        return wert.replace(tzinfo=timezone.utc)
    return wert


@router.post(
    "/positionen/{position_id}/besetzungen",
    response_model=BesetzungErgebnis,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(*SCHREIBEN))],
)
async def create_besetzung(
    position_id: UUID,
    body: BesetzungCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> BesetzungErgebnis:
    mandant_id = _mandant(auth)
    akteur = await _schreib_akteur(session, auth)
    # Eine Besetzung gewaehrt alle Rechte der Position: wie Rechtevergabe behandelt.
    esk.rechte_verwalten_pflicht(akteur)
    position = await _position(session, auth, position_id)
    await esk.position_im_scope_pruefen(session, akteur, esk.RECHTE_VERWALTEN, [position.id])
    if position.archiviert_am is not None:
        raise _konflikt("Auf eine archivierte Position kann niemand gesetzt werden")

    von = _aware(body.gueltig_von) or org.jetzt()
    bis = _aware(body.gueltig_bis)
    if body.art == "vertretung" and bis is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Eine Vertretung braucht ein Enddatum (gueltig_bis)"
        )
    if bis is not None and bis <= von:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="gueltig_bis muss nach gueltig_von liegen"
        )

    ziel = await session.get(User, body.user_id)
    if ziel is None or ziel.mandant_id != mandant_id:
        raise _nicht_gefunden("Nutzer")
    if not await zuweisbare_user_ids(session, {ziel.id}):
        raise _konflikt("Der Nutzer ist deaktiviert und kann keiner Position zugewiesen werden")
    if bis is None and (
        await session.scalar(
            select(func.count()).select_from(PositionBesetzung).where(
                PositionBesetzung.position_id == position.id,
                PositionBesetzung.user_id == ziel.id,
                PositionBesetzung.gueltig_bis.is_(None),
            )
        )
    ):
        raise _konflikt("Der Nutzer ist dieser Position bereits zugewiesen")

    overrides = [
        (o.bereich, o.aktion, o.wirkung, o.scope)
        for o in (
            await session.execute(select(PositionRecht).where(PositionRecht.position_id == position.id))
        ).scalars()
    ]
    esk.mehr_rechte_pruefen(akteur, await esk.position_rechte_map(session, position.account_typ_id, overrides))

    async with esk.verwaltung_bleibt_erhalten(session, mandant_id):
        besetzung = PositionBesetzung(
            mandant_id=mandant_id,
            position_id=position.id,
            user_id=ziel.id,
            art=body.art,
            gueltig_von=von,
            gueltig_bis=bis,
        )
        session.add(besetzung)
        await session.flush()
        bs.cache_leeren(session)

    warnung = None
    if body.art == "regulaer":
        aktive = (await org.aktive_besetzungen(session, mandant_id, max(org.jetzt(), von), position.id)).get(
            position.id, []
        )
        regulaer = sum(1 for b in aktive if b.art == "regulaer")
        if regulaer > position.soll_besetzung:
            warnung = (
                f"Soll-Besetzung überschritten: {regulaer} von {position.soll_besetzung} "
                "vorgesehenen Besetzungen"
            )
    await log_aenderung(
        session,
        aktion="besetzung_angelegt",
        mandant_id=mandant_id,
        actor_user_id=auth.user_id,
        entity_type="besetzung",
        entity_id=besetzung.id,
        vorher=None,
        nachher=org.besetzung_snapshot(besetzung),
    )
    darf = await _namens_filter(session, akteur)
    reads = await _besetzung_reads(session, [besetzung], darf)
    return BesetzungErgebnis(besetzung=reads[besetzung.id], warnung=warnung)


@router.patch(
    "/besetzungen/{besetzung_id}",
    response_model=BesetzungErgebnis,
    response_model_exclude_unset=True,
    dependencies=[Depends(require_roles(*SCHREIBEN))],
)
async def update_besetzung(
    besetzung_id: UUID,
    body: BesetzungUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> BesetzungErgebnis:
    """gueltig_bis setzen = Freistellung/Ende (ohne Angabe: jetzt)."""
    mandant_id = _mandant(auth)
    akteur = await _schreib_akteur(session, auth)
    schluessel = (("organigramm", "bearbeiten"), *esk.RECHTE_VERWALTEN)
    if not akteur.hat_eines(schluessel):
        raise esk.verboten("Keine Berechtigung für diese Aktion")
    besetzung = (
        await session.execute(
            select(PositionBesetzung).where(
                PositionBesetzung.id == besetzung_id, PositionBesetzung.mandant_id == mandant_id
            )
        )
    ).scalar_one_or_none()
    if besetzung is None:
        raise _nicht_gefunden("Besetzung")
    await esk.position_im_scope_pruefen(session, akteur, schluessel, [besetzung.position_id])

    jetzt = org.jetzt()
    if besetzung.gueltig_bis is not None and besetzung.gueltig_bis <= jetzt:
        raise _konflikt("Die Besetzung ist bereits beendet")
    neues_ende = _aware(body.gueltig_bis) or jetzt
    if neues_ende <= besetzung.gueltig_von:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Das Ende muss nach dem Beginn der Besetzung liegen"
        )
    vorher = org.besetzung_snapshot(besetzung)
    async with esk.verwaltung_bleibt_erhalten(session, mandant_id):
        besetzung.gueltig_bis = neues_ende
        await session.flush()
        bs.cache_leeren(session)
    await log_aenderung(
        session,
        aktion="besetzung_beendet",
        mandant_id=mandant_id,
        actor_user_id=auth.user_id,
        entity_type="besetzung",
        entity_id=besetzung.id,
        vorher=vorher,
        nachher=org.besetzung_snapshot(besetzung),
    )
    darf = await _namens_filter(session, akteur)
    reads = await _besetzung_reads(session, [besetzung], darf)
    return BesetzungErgebnis(besetzung=reads[besetzung.id])


# --- Rechte-Overrides -------------------------------------------------------------


def _tupel(eintraege: list[RechtOverrideIn]) -> list[esk.OverrideTupel]:
    return [(e.bereich, e.aktion, e.wirkung, e.scope) for e in eintraege]


def _doppelte_pruefen(eintraege: list[RechtOverrideIn]) -> None:
    gesehen: set[tuple[str, str]] = set()
    for e in eintraege:
        if (e.bereich, e.aktion) in gesehen:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Das Recht „{e.bereich}.{e.aktion}“ ist mehrfach angegeben",
            )
        gesehen.add((e.bereich, e.aktion))


@router.put(
    "/positionen/{position_id}/rechte",
    response_model=list[RechtOverrideRead],
    dependencies=[Depends(require_roles(*SCHREIBEN))],
)
async def set_position_rechte(
    position_id: UUID,
    body: list[RechtOverrideIn],
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[RechtOverrideRead]:
    mandant_id = _mandant(auth)
    akteur = await _schreib_akteur(session, auth)
    esk.rechte_verwalten_pflicht(akteur)
    _doppelte_pruefen(body)
    position = await _position(session, auth, position_id)
    await esk.position_im_scope_pruefen(session, akteur, esk.RECHTE_VERWALTEN, [position.id])

    bisher = list(
        (await session.execute(select(PositionRecht).where(PositionRecht.position_id == position.id))).scalars()
    )
    alt = await esk.position_rechte_map(
        session, position.account_typ_id, [(o.bereich, o.aktion, o.wirkung, o.scope) for o in bisher]
    )
    neu = await esk.position_rechte_map(session, position.account_typ_id, _tupel(body))
    # Auch das Aufheben einer Verweigerung stellt Typ-Rechte wieder her und zaehlt als Vergabe.
    esk.mehr_rechte_pruefen(akteur, neu, alt)

    vorher = org.overrides_snapshot(bisher)
    async with esk.verwaltung_bleibt_erhalten(session, mandant_id):
        await session.execute(sa_delete(PositionRecht).where(PositionRecht.position_id == position.id))
        for e in body:
            session.add(
                PositionRecht(
                    mandant_id=mandant_id,
                    position_id=position.id,
                    bereich=e.bereich,
                    aktion=e.aktion,
                    wirkung=e.wirkung,
                    scope=e.scope,
                )
            )
        await session.flush()
        bs.cache_leeren(session)
    nachher = [
        {"bereich": e.bereich, "aktion": e.aktion, "wirkung": e.wirkung, "scope": e.scope} for e in body
    ]
    nachher.sort(key=lambda e: (e["bereich"], e["aktion"]))
    await log_aenderung(
        session,
        aktion="position_rechte_geaendert",
        mandant_id=mandant_id,
        actor_user_id=auth.user_id,
        entity_type="position",
        entity_id=position.id,
        vorher={"overrides": vorher},
        nachher={"overrides": nachher},
    )
    return [RechtOverrideRead(**e) for e in nachher]


@router.put(
    "/users/{user_id}/rechte",
    response_model=list[RechtOverrideRead],
    dependencies=[Depends(require_roles(*SCHREIBEN))],
)
async def set_user_rechte(
    user_id: UUID,
    body: list[RechtOverrideIn],
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[RechtOverrideRead]:
    mandant_id = _mandant(auth)
    akteur = await _schreib_akteur(session, auth)
    esk.rechte_verwalten_pflicht(akteur)
    _doppelte_pruefen(body)
    ziel = await session.get(User, user_id)
    if ziel is None or ziel.mandant_id != mandant_id:
        raise _nicht_gefunden("Nutzer")
    await esk.user_im_scope_pruefen(session, akteur, esk.RECHTE_VERWALTEN, ziel.id)

    bisher = list(
        (await session.execute(select(UserRecht).where(UserRecht.user_id == ziel.id))).scalars()
    )
    esk.mehr_rechte_pruefen(
        akteur,
        esk.user_override_map(_tupel(body)),
        esk.user_override_map([(o.bereich, o.aktion, o.wirkung, o.scope) for o in bisher]),
    )
    effektiv_vorher = await esk.user_effektiv_map(session, ziel)

    vorher = org.overrides_snapshot(bisher)
    async with esk.verwaltung_bleibt_erhalten(session, mandant_id):
        await session.execute(sa_delete(UserRecht).where(UserRecht.user_id == ziel.id))
        for e in body:
            session.add(
                UserRecht(
                    mandant_id=mandant_id,
                    user_id=ziel.id,
                    bereich=e.bereich,
                    aktion=e.aktion,
                    wirkung=e.wirkung,
                    scope=e.scope,
                )
            )
        await session.flush()
        bs.cache_leeren(session)
        # Aufheben einer Verweigerung o. ae.: am aufgeloesten Ergebnis pruefen.
        esk.mehr_rechte_pruefen(akteur, await esk.user_effektiv_map(session, ziel), effektiv_vorher)
    nachher = [
        {"bereich": e.bereich, "aktion": e.aktion, "wirkung": e.wirkung, "scope": e.scope} for e in body
    ]
    nachher.sort(key=lambda e: (e["bereich"], e["aktion"]))
    await log_aenderung(
        session,
        aktion="user_rechte_geaendert",
        mandant_id=mandant_id,
        actor_user_id=auth.user_id,
        entity_type="user",
        entity_id=ziel.id,
        vorher={"overrides": vorher},
        nachher={"overrides": nachher},
    )
    return [RechtOverrideRead(**e) for e in nachher]


# --- Organisationseinheiten ---------------------------------------------------------


def _mandantweit_pruefen(akteur: esk.Akteur, aktion: str) -> None:
    esk.recht_pflicht(akteur, "organigramm", aktion)
    if not akteur.ist_admin and akteur.rechte.scope("organigramm", aktion) != "mandant":
        raise esk.verboten("Organisationseinheiten können nur mit mandantweiter Berechtigung geändert werden")


def _einheit_snapshot(e: OrgEinheit) -> dict:
    return {"id": e.id, "name": e.name, "typ": e.typ, "parent_id": e.parent_id, "archiviert_am": e.archiviert_am}


@router.post(
    "/org-einheiten",
    response_model=OrgEinheitRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(*SCHREIBEN))],
)
async def create_org_einheit(
    body: OrgEinheitCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> OrgEinheitRead:
    mandant_id = _mandant(auth)
    akteur = await _schreib_akteur(session, auth)
    _mandantweit_pruefen(akteur, "erstellen")
    await org.baum_sperren(session, mandant_id)
    if body.parent_id is not None:
        parent = await _einheit(session, auth, body.parent_id)
        if parent.archiviert_am is not None:
            raise _konflikt("Unter einer archivierten Organisationseinheit kann nichts angelegt werden")
    einheit = OrgEinheit(mandant_id=mandant_id, name=body.name.strip(), typ=body.typ, parent_id=body.parent_id)
    session.add(einheit)
    await session.flush()
    await log_aenderung(
        session,
        aktion="org_einheit_erstellt",
        mandant_id=mandant_id,
        actor_user_id=auth.user_id,
        entity_type="org_einheit",
        entity_id=einheit.id,
        vorher=None,
        nachher=_einheit_snapshot(einheit),
    )
    return OrgEinheitRead.model_validate(einheit, from_attributes=True)


@router.patch(
    "/org-einheiten/{einheit_id}",
    response_model=OrgEinheitRead,
    dependencies=[Depends(require_roles(*SCHREIBEN))],
)
async def update_org_einheit(
    einheit_id: UUID,
    body: OrgEinheitUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> OrgEinheitRead:
    mandant_id = _mandant(auth)
    akteur = await _schreib_akteur(session, auth)
    _mandantweit_pruefen(akteur, "bearbeiten")
    await org.baum_sperren(session, mandant_id)
    einheit = await _einheit(session, auth, einheit_id)
    if einheit.archiviert_am is not None:
        raise _konflikt("Archivierte Organisationseinheiten können nicht bearbeitet werden")
    aenderungen = body.model_dump(exclude_unset=True)
    if aenderungen.get("name") is None:
        aenderungen.pop("name", None)
    if aenderungen.get("typ") is None:
        aenderungen.pop("typ", None)
    if "name" in aenderungen:
        aenderungen["name"] = aenderungen["name"].strip()
    if "parent_id" in aenderungen and aenderungen["parent_id"] != einheit.parent_id:
        neuer_parent_id = aenderungen["parent_id"]
        if neuer_parent_id is not None:
            parent = await _einheit(session, auth, neuer_parent_id)
            if parent.archiviert_am is not None:
                raise _konflikt("Unter einer archivierten Organisationseinheit kann nichts eingehängt werden")
            if einheit.id in await org.pfad_zur_wurzel(session, "org_einheiten", mandant_id, parent.id):
                raise _konflikt(
                    "Eine Organisationseinheit kann nicht unter sich selbst oder ihre Untereinheiten gehängt werden"
                )
    vorher = _einheit_snapshot(einheit)
    for feld, wert in aenderungen.items():
        setattr(einheit, feld, wert)
    await session.flush()
    await session.refresh(einheit)
    nachher = _einheit_snapshot(einheit)
    geaendert = {k for k in nachher if nachher[k] != vorher[k]}
    if geaendert:
        await log_aenderung(
            session,
            aktion="org_einheit_geaendert",
            mandant_id=mandant_id,
            actor_user_id=auth.user_id,
            entity_type="org_einheit",
            entity_id=einheit.id,
            vorher={k: vorher[k] for k in geaendert},
            nachher={k: nachher[k] for k in geaendert},
        )
    return OrgEinheitRead.model_validate(einheit, from_attributes=True)


@router.post(
    "/org-einheiten/{einheit_id}/archivieren",
    response_model=OrgEinheitRead,
    dependencies=[Depends(require_roles(*SCHREIBEN))],
)
async def archive_org_einheit(
    einheit_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> OrgEinheitRead:
    mandant_id = _mandant(auth)
    akteur = await _schreib_akteur(session, auth)
    _mandantweit_pruefen(akteur, "loeschen")
    await org.baum_sperren(session, mandant_id)
    einheit = await _einheit(session, auth, einheit_id)
    if einheit.archiviert_am is not None:
        raise _konflikt("Die Organisationseinheit ist bereits archiviert")
    kinder = await session.scalar(
        select(func.count()).select_from(OrgEinheit).where(
            OrgEinheit.parent_id == einheit.id, OrgEinheit.archiviert_am.is_(None)
        )
    )
    if kinder:
        raise _konflikt(f"Die Organisationseinheit hat noch {kinder} Untereinheit(en)")
    positionen = await session.scalar(
        select(func.count()).select_from(Position).where(
            Position.org_einheit_id == einheit.id, Position.archiviert_am.is_(None)
        )
    )
    if positionen:
        raise _konflikt(f"Der Organisationseinheit sind noch {positionen} Position(en) zugeordnet")
    vorher = _einheit_snapshot(einheit)
    einheit.archiviert_am = org.jetzt()
    await session.flush()
    await log_aenderung(
        session,
        aktion="org_einheit_archiviert",
        mandant_id=mandant_id,
        actor_user_id=auth.user_id,
        entity_type="org_einheit",
        entity_id=einheit.id,
        vorher=vorher,
        nachher=_einheit_snapshot(einheit),
    )
    return OrgEinheitRead.model_validate(einheit, from_attributes=True)


@router.delete(
    "/org-einheiten/{einheit_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(*SCHREIBEN))],
)
async def delete_org_einheit(
    einheit_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    mandant_id = _mandant(auth)
    akteur = await _schreib_akteur(session, auth)
    _mandantweit_pruefen(akteur, "loeschen")
    await org.baum_sperren(session, mandant_id)
    einheit = await _einheit(session, auth, einheit_id)
    kinder = await session.scalar(
        select(func.count()).select_from(OrgEinheit).where(OrgEinheit.parent_id == einheit.id)
    )
    if kinder:
        raise _konflikt("Die Organisationseinheit hat Untereinheiten und kann nicht gelöscht werden")
    positionen = await session.scalar(
        select(func.count()).select_from(Position).where(Position.org_einheit_id == einheit.id)
    )
    if positionen:
        raise _konflikt("Der Organisationseinheit sind Positionen zugeordnet – nur archivieren")
    vorher = _einheit_snapshot(einheit)
    await session.delete(einheit)
    await session.flush()
    await log_aenderung(
        session,
        aktion="org_einheit_geloescht",
        mandant_id=mandant_id,
        actor_user_id=auth.user_id,
        entity_type="org_einheit",
        entity_id=einheit_id,
        vorher=vorher,
        nachher=None,
    )
