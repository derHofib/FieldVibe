from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.account_typ import AccountTyp, AccountTypRecht, aktionen_fuer_bereich
from app.models.organigramm import Position
from app.models.user import User
from app.schemas.account_typ import (
    AccountTypCreate,
    AccountTypRead,
    AccountTypUpdate,
    RechteMatrixEintrag,
    RechtSetzen,
)
from app.services import berechtigung_service as bs
from app.services import eskalation_service as esk
from app.services.audit_service import log_aenderung
from app.services.organigramm_sync_service import (
    account_typ_flag_in_scope_uebersetzen,
    position_fuer_account_typ_anlegen,
    scope_fuer_neues_recht,
    typ_position_umbenennen,
)
from app.services.rechte_service import rechte_matrix_fuer_account_typ

router = APIRouter(
    prefix="/api/account-typen",
    tags=["account-typen"],
    # mandant_admin (und loesch_operativ) wie bisher; custom nur mit rechte_verwalten,
    # dann mit Eskalationsschutz (siehe _verwalter und app/services/eskalation_service.py).
    dependencies=[Depends(require_roles("mandant_admin", "custom"))],
)

_FLAGS = (
    "darf_vorgaenge_selbst_uebernehmen",
    "darf_zeiten_buchen",
    "darf_abwesenheiten_verwalten",
)


async def _verwalter(session: AsyncSession, auth: AuthContext) -> esk.Akteur:
    akteur = await esk.akteur_laden(session, auth)
    esk.rechte_verwalten_pflicht(akteur)
    return akteur


def _snapshot(typ: AccountTyp) -> dict:
    return {
        "id": typ.id,
        "name": typ.name,
        "icon": typ.icon,
        "farbe": typ.farbe,
        "nur_zugewiesene_kunden": typ.nur_zugewiesene_kunden,
        "darf_vorgaenge_selbst_uebernehmen": typ.darf_vorgaenge_selbst_uebernehmen,
        "darf_zeiten_buchen": typ.darf_zeiten_buchen,
        "darf_abwesenheiten_verwalten": typ.darf_abwesenheiten_verwalten,
        "reihenfolge": typ.reihenfolge,
    }


async def _anzahl_nutzer(session: AsyncSession, account_typ_id: UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(User).where(User.account_typ_id == account_typ_id)
    )
    return result.scalar_one()


async def _to_read(session: AsyncSession, typ: AccountTyp) -> AccountTypRead:
    return AccountTypRead(
        id=typ.id,
        name=typ.name,
        icon=typ.icon,
        farbe=typ.farbe,
        nur_zugewiesene_kunden=typ.nur_zugewiesene_kunden,
        darf_vorgaenge_selbst_uebernehmen=typ.darf_vorgaenge_selbst_uebernehmen,
        darf_zeiten_buchen=typ.darf_zeiten_buchen,
        darf_abwesenheiten_verwalten=typ.darf_abwesenheiten_verwalten,
        reihenfolge=typ.reihenfolge,
        anzahl_nutzer=await _anzahl_nutzer(session, typ.id),
    )


@router.get("", response_model=list[AccountTypRead])
async def list_account_typen(
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[AccountTypRead]:
    await _verwalter(session, auth)
    result = await session.execute(
        select(AccountTyp)
        .where(AccountTyp.mandant_id == auth.mandant_id)
        .order_by(AccountTyp.reihenfolge, AccountTyp.name)
    )
    return [await _to_read(session, typ) for typ in result.scalars().all()]


@router.post("", response_model=AccountTypRead, status_code=status.HTTP_201_CREATED)
async def create_account_typ(
    body: AccountTypCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AccountTypRead:
    akteur = await _verwalter(session, auth)
    esk.flags_pruefen(akteur, [f for f in _FLAGS if getattr(body, f)])
    typ = AccountTyp(
        mandant_id=auth.mandant_id,
        name=body.name.strip(),
        icon=body.icon,
        farbe=body.farbe,
        nur_zugewiesene_kunden=body.nur_zugewiesene_kunden,
        darf_vorgaenge_selbst_uebernehmen=body.darf_vorgaenge_selbst_uebernehmen,
        darf_zeiten_buchen=body.darf_zeiten_buchen,
        darf_abwesenheiten_verwalten=body.darf_abwesenheiten_verwalten,
    )
    session.add(typ)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ein Account-Typ mit diesem Namen existiert bereits",
        ) from exc
    # Jeder Typ ist zugleich Vorlage-Position im Organigramm (unter der Wurzel).
    await position_fuer_account_typ_anlegen(session, typ)
    await log_aenderung(
        session,
        aktion="account_typ_erstellt",
        mandant_id=typ.mandant_id,
        actor_user_id=auth.user_id,
        entity_type="account_typ",
        entity_id=typ.id,
        vorher=None,
        nachher=_snapshot(typ),
    )
    return await _to_read(session, typ)


@router.patch("/{account_typ_id}", response_model=AccountTypRead)
async def update_account_typ(
    account_typ_id: UUID,
    body: AccountTypUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AccountTypRead:
    akteur = await _verwalter(session, auth)
    typ = await session.get(AccountTyp, account_typ_id)
    if typ is None or typ.mandant_id != auth.mandant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account-Typ nicht gefunden")
    await esk.typ_im_scope_pruefen(session, akteur, typ.id)
    aenderungen = body.model_dump(exclude_unset=True)
    esk.flags_pruefen(
        akteur, [f for f in _FLAGS if aenderungen.get(f) is True and not getattr(typ, f)]
    )
    vorher = _snapshot(typ)
    alte_rechte = await esk.typ_rechte_map(session, typ.id)
    alter_name, altes_flag = typ.name, typ.nur_zugewiesene_kunden
    async with esk.verwaltung_bleibt_erhalten(session, typ.mandant_id):
        for feld, wert in aenderungen.items():
            setattr(typ, feld, wert.strip() if feld == "name" and isinstance(wert, str) else wert)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ein Account-Typ mit diesem Namen existiert bereits",
            ) from exc
        await typ_position_umbenennen(session, typ, alter_name=alter_name)
        if typ.nur_zugewiesene_kunden != altes_flag:
            await account_typ_flag_in_scope_uebersetzen(
                session, typ, nur_zugewiesene_kunden=typ.nur_zugewiesene_kunden
            )
            await session.flush()
            # Das Flag false setzt Scopes eigene -> mandant: das ist eine Rechte-Erweiterung.
            esk.mehr_rechte_pruefen(akteur, await esk.typ_rechte_map(session, typ.id), alte_rechte)
    nachher = _snapshot(typ)
    geaendert = {k for k in nachher if nachher[k] != vorher[k]}
    if geaendert:
        await log_aenderung(
            session,
            aktion="account_typ_geaendert",
            mandant_id=typ.mandant_id,
            actor_user_id=auth.user_id,
            entity_type="account_typ",
            entity_id=typ.id,
            vorher={k: vorher[k] for k in geaendert},
            nachher={k: nachher[k] for k in geaendert},
        )
    return await _to_read(session, typ)


@router.delete("/{account_typ_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account_typ(
    account_typ_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    akteur = await _verwalter(session, auth)
    typ = await session.get(AccountTyp, account_typ_id)
    if typ is None or typ.mandant_id != auth.mandant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account-Typ nicht gefunden")
    await esk.typ_im_scope_pruefen(session, akteur, typ.id)
    if await _anzahl_nutzer(session, account_typ_id) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Diesem Account-Typ sind noch Nutzer zugeordnet",
        )
    # Positionen des Typs (aus Migration 0102) haengen per RESTRICT daran: Kinder
    # an den Elternknoten umhaengen, dann Position loeschen (Besetzungen: CASCADE;
    # Nutzer gibt es keine mehr, siehe Pruefung oben).
    for position in (
        await session.execute(select(Position).where(Position.account_typ_id == account_typ_id))
    ).scalars().all():
        await session.execute(
            update(Position).where(Position.parent_id == position.id).values(parent_id=position.parent_id)
        )
        await session.delete(position)
    await session.flush()
    await session.execute(
        AccountTypRecht.__table__.delete().where(AccountTypRecht.account_typ_id == account_typ_id)
    )
    vorher = _snapshot(typ)
    await session.delete(typ)
    await session.flush()
    await log_aenderung(
        session,
        aktion="account_typ_geloescht",
        mandant_id=auth.mandant_id,
        actor_user_id=auth.user_id,
        entity_type="account_typ",
        entity_id=account_typ_id,
        vorher=vorher,
        nachher=None,
    )


@router.get("/{account_typ_id}/rechte", response_model=list[RechteMatrixEintrag])
async def get_rechte(
    account_typ_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[RechteMatrixEintrag]:
    await _verwalter(session, auth)
    typ = await session.get(AccountTyp, account_typ_id)
    if typ is None or typ.mandant_id != auth.mandant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account-Typ nicht gefunden")
    matrix = await rechte_matrix_fuer_account_typ(session, account_typ_id)
    return [
        RechteMatrixEintrag(bereich=bereich, aktion=aktion, erlaubt=erlaubt)
        for bereich, aktionen in matrix.items()
        for aktion, erlaubt in aktionen.items()
    ]


@router.put("/{account_typ_id}/rechte", response_model=list[RechteMatrixEintrag])
async def set_recht(
    account_typ_id: UUID,
    body: RechtSetzen,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[RechteMatrixEintrag]:
    akteur = await _verwalter(session, auth)
    typ = await session.get(AccountTyp, account_typ_id)
    if typ is None or typ.mandant_id != auth.mandant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account-Typ nicht gefunden")
    await esk.typ_im_scope_pruefen(session, akteur, typ.id)
    if body.aktion not in aktionen_fuer_bereich(body.bereich):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Diese Aktion gibt es für diesen Bereich nicht",
        )
    result = await session.execute(
        select(AccountTypRecht).where(
            AccountTypRecht.account_typ_id == account_typ_id,
            AccountTypRecht.bereich == body.bereich,
            AccountTypRecht.aktion == body.aktion,
        )
    )
    eintrag = result.scalar_one_or_none()
    vorher = {"erlaubt": bool(eintrag.erlaubt), "scope": eintrag.scope} if eintrag is not None else None
    if body.erlaubt and not (eintrag is not None and eintrag.erlaubt):
        # Nur vergeben, was man selbst mit mindestens diesem Scope hat.
        neuer_scope = eintrag.scope if eintrag is not None else scope_fuer_neues_recht(typ, body.bereich)
        esk.mehr_rechte_pruefen(akteur, {(body.bereich, body.aktion): neuer_scope})
    async with esk.verwaltung_bleibt_erhalten(session, typ.mandant_id):
        if eintrag is None:
            eintrag = AccountTypRecht(
                mandant_id=typ.mandant_id,
                account_typ_id=account_typ_id,
                bereich=body.bereich,
                aktion=body.aktion,
                erlaubt=body.erlaubt,
                scope=scope_fuer_neues_recht(typ, body.bereich),
            )
            session.add(eintrag)
        else:
            eintrag.erlaubt = body.erlaubt
        await session.flush()
        bs.cache_leeren(session)
    await log_aenderung(
        session,
        aktion="account_typ_recht_geaendert",
        mandant_id=typ.mandant_id,
        actor_user_id=auth.user_id,
        entity_type="account_typ",
        entity_id=typ.id,
        vorher={"bereich": body.bereich, "aktion": body.aktion, **(vorher or {"erlaubt": False, "scope": None})},
        nachher={"bereich": body.bereich, "aktion": body.aktion, "erlaubt": eintrag.erlaubt, "scope": eintrag.scope},
    )

    matrix = await rechte_matrix_fuer_account_typ(session, account_typ_id)
    return [
        RechteMatrixEintrag(bereich=bereich, aktion=aktion, erlaubt=erlaubt)
        for bereich, aktionen in matrix.items()
        for aktion, erlaubt in aktionen.items()
    ]
