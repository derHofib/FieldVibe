from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_recht, require_roles
from app.core.security import hash_password
from app.db.session import system_session
from app.models.account_typ import AccountTyp
from app.models.einladung import Einladung
from app.models.mandant import Mandant
from app.models.user import User
from app.schemas.einladung import EinladungRead, MitarbeiterEinladungCreate
from app.schemas.user import BottomNavUpdate, OfficeNavUpdate, UserCreate, UserRead, UserUpdate
from app.services import eskalation_service as esk
from app.services.audit_service import log_action, log_aenderung
from app.services.organigramm_sync_service import besetzung_pflegen
from app.services.einladung_service import (
    create_einladung,
    registrierungslink_erzeugen,
    to_read_model,
    versende_einladung,
)
from app.services.token_widerruf_service import widerrufe_tokens
from app.services.user_anonymisierung_service import (
    anonymisiere_user,
    ist_anonymisiert,
    nicht_anonymisiert,
)

router = APIRouter(prefix="/api/users", tags=["users"])

# Siehe app/services/papierkorb_service.py: nur super_admin darf diese
# Rollen vergeben/entziehen -- weder ein mandant_admin noch ein
# loesch_operativ (das via app/api/deps.py:require_roles() ansonsten
# ueberall dieselben Rechte wie mandant_admin hat) sollen sich diese
# Berechtigung selbst zuweisen bzw. sie weiterreichen koennen.
_PAPIERKORB_ROLLEN = ("loesch_ansicht", "loesch_operativ")


def _integrity_error_detail(exc: IntegrityError) -> str:
    constraint = getattr(getattr(exc, "orig", None), "constraint_name", None)
    if constraint == "uq_users_mandant_loesch_operativ_aktiv":
        return "Für diesen Mandanten existiert bereits ein aktiver loesch_operativ-Account"
    return "E-Mail bereits vergeben"


async def _to_read(session: AsyncSession, user: User) -> UserRead:
    account_typ = (
        await session.get(AccountTyp, user.account_typ_id)
        if user.account_typ_id is not None
        else None
    )
    return UserRead(
        id=user.id,
        mandant_id=user.mandant_id,
        email=user.email,
        role=user.role,
        account_typ_id=user.account_typ_id,
        account_typ_name=account_typ.name if account_typ is not None else None,
        nur_zugewiesene_kunden=account_typ.nur_zugewiesene_kunden if account_typ is not None else False,
        name=user.name,
        avatar_url=user.avatar_url,
        aktiv=user.aktiv,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


async def _custom_account_typ_pruefen(
    session: AsyncSession, auth: AuthContext, user: User, body: UserUpdate
) -> None:
    if user.mandant_id != auth.mandant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden")
    if set(body.model_dump(exclude_unset=True)) - {"account_typ_id"}:
        raise esk.verboten("Mit Ihrer Berechtigung kann nur der Account-Typ geändert werden")
    akteur = await esk.akteur_laden(session, auth)
    esk.rechte_verwalten_pflicht(akteur)
    if user.role != "custom":
        raise esk.verboten("Die Rolle dieses Accounts kann mit Ihrer Berechtigung nicht geändert werden")
    await esk.user_im_scope_pruefen(session, akteur, esk.RECHTE_VERWALTEN, user.id)
    typ = await session.get(AccountTyp, body.account_typ_id) if body.account_typ_id else None
    if typ is not None and typ.mandant_id == user.mandant_id:
        esk.mehr_rechte_pruefen(akteur, await esk.typ_rechte_map(session, typ.id))
        esk.flags_pruefen(
            akteur,
            [
                f
                for f in (
                    "darf_vorgaenge_selbst_uebernehmen",
                    "darf_zeiten_buchen",
                    "darf_abwesenheiten_verwalten",
                )
                if getattr(typ, f)
            ],
        )


@router.get(
    "/einladungen",
    response_model=list[EinladungRead],
    dependencies=[Depends(require_roles("super_admin", "mandant_admin"))],
)
async def list_einladungen(session: AsyncSession = Depends(get_db)) -> list[EinladungRead]:
    result = await session.execute(
        select(Einladung)
        .where(
            Einladung.art == "mitarbeiter",
            or_(Einladung.rolle.is_(None), Einladung.rolle != "super_admin"),
        )
        .order_by(Einladung.created_at.desc())
    )
    return [
        EinladungRead(
            **to_read_model(
                e, registrierungslink=registrierungslink_erzeugen(e) if e.status == "offen" else None
            )
        )
        for e in result.scalars().all()
    ]


@router.post(
    "/einladungen",
    response_model=EinladungRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("super_admin", "mandant_admin"))],
)
async def mitarbeiter_einladen(
    body: MitarbeiterEinladungCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> EinladungRead:
    if auth.role == "mandant_admin":
        if body.mandant_id is not None and body.mandant_id != auth.mandant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Einladungen können nur in den eigenen Mandanten verschickt werden",
            )
        ziel_mandant_id = auth.mandant_id
    else:
        if body.mandant_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="mandant_id ist erforderlich"
            )
        ziel_mandant_id = body.mandant_id

    mandant = await session.get(Mandant, ziel_mandant_id)
    if mandant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mandant nicht gefunden")

    if body.role == "custom":
        account_typ = await session.get(AccountTyp, body.account_typ_id)
        if account_typ is None or account_typ.mandant_id != ziel_mandant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account-Typ nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )

    einladender = await session.get(User, auth.user_id)
    einladung = await create_einladung(
        session,
        mandant_id=ziel_mandant_id,
        email=body.email,
        art="mitarbeiter",
        rolle=body.role,
        account_typ_id=body.account_typ_id,
        eingeladen_von=auth.user_id,
    )
    await versende_einladung(
        session,
        einladung,
        absender_name=einladender.name if einladender else mandant.name,
        absender_rolle=einladender.role if einladender else None,
    )
    link = registrierungslink_erzeugen(einladung)

    await log_action(
        session,
        aktion="mitarbeiter_eingeladen",
        mandant_id=ziel_mandant_id,
        actor_user_id=auth.user_id,
        entity_type="einladung",
        entity_id=einladung.id,
        payload={"email": einladung.email, "role": einladung.rolle},
    )
    return EinladungRead(**to_read_model(einladung, registrierungslink=link))


@router.post(
    "/einladungen/{einladung_id}/erneut-senden",
    response_model=EinladungRead,
    dependencies=[Depends(require_roles("super_admin", "mandant_admin"))],
)
async def einladung_erneut_senden(
    einladung_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> EinladungRead:
    einladung = await session.get(Einladung, einladung_id)
    if einladung is None or einladung.art != "mitarbeiter" or einladung.status != "offen":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Einladung nicht gefunden")

    einladender = await session.get(User, auth.user_id)
    mandant = await session.get(Mandant, einladung.mandant_id)
    await versende_einladung(
        session,
        einladung,
        absender_name=einladender.name if einladender else mandant.name,
        absender_rolle=einladender.role if einladender else None,
    )
    link = registrierungslink_erzeugen(einladung)
    return EinladungRead(**to_read_model(einladung, registrierungslink=link))


@router.delete(
    "/einladungen/{einladung_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("super_admin", "mandant_admin"))],
)
async def einladung_widerrufen(
    einladung_id: UUID, session: AsyncSession = Depends(get_db)
) -> None:
    einladung = await session.get(Einladung, einladung_id)
    if einladung is None or einladung.art != "mitarbeiter" or einladung.status != "offen":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Einladung nicht gefunden")
    einladung.status = "widerrufen"
    await session.flush()


@router.get(
    "",
    response_model=list[UserRead],
    dependencies=[
        Depends(require_roles("super_admin", "mandant_admin", "custom")),
        Depends(require_recht("mitarbeiterverwaltung", "sehen")),
    ],
)
async def list_users(
    versteckte: bool = False,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[UserRead]:
    # RLS restricts a mandant_admin's session to their own mandant already;
    # super_admin sessions bypass RLS and therefore see every account.
    # Read-only for custom account types too: colleagues' names are needed
    # for the @-mention picker in the Vorgangs-Chat (Phase 3) and aren't
    # sensitive the way account management (create/patch below) is.
    # Anonymisierte Nutzer (siehe user_anonymisierung_service) sind nie
    # auswaehlbar. `versteckte` ist kein Sicherheitsmerkmal, nur eine
    # Ausblendung der Papierkorb-Accounts in der Standardansicht.
    stmt = select(User).where(nicht_anonymisiert())
    if auth.mandant_id is not None:
        # Mandanten-Kontext (auch Impersonation): Plattform-Admins gehoeren
        # nicht in die Nutzerliste des Mandanten.
        stmt = stmt.where(User.role != "super_admin")
    if not versteckte:
        stmt = stmt.where(User.role.not_in(_PAPIERKORB_ROLLEN))
    result = await session.execute(stmt.order_by(User.name))
    users = list(result.scalars().all())

    account_typ_ids = {u.account_typ_id for u in users if u.account_typ_id is not None}
    account_typen: dict[UUID, AccountTyp] = {}
    if account_typ_ids:
        typen_result = await session.execute(
            select(AccountTyp).where(AccountTyp.id.in_(account_typ_ids))
        )
        account_typen = {t.id: t for t in typen_result.scalars().all()}

    return [
        UserRead(
            id=u.id,
            mandant_id=u.mandant_id,
            email=u.email,
            role=u.role,
            account_typ_id=u.account_typ_id,
            account_typ_name=account_typen[u.account_typ_id].name if u.account_typ_id in account_typen else None,
            nur_zugewiesene_kunden=account_typen[u.account_typ_id].nur_zugewiesene_kunden
            if u.account_typ_id in account_typen
            else False,
            name=u.name,
            avatar_url=u.avatar_url,
            aktiv=u.aktiv,
            created_at=u.created_at,
            updated_at=u.updated_at,
        )
        for u in users
    ]


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("super_admin", "mandant_admin"))],
)
async def create_user(
    body: UserCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> UserRead:
    if auth.role in ("mandant_admin", "loesch_operativ"):
        if body.role == "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="mandant_admin darf keine super_admin-Accounts anlegen",
            )
        # Papierkorb-Rollen (siehe app/services/papierkorb_service.py) sind
        # bewusst nur durch super_admin vergebbar -- loesch_operativ sieht
        # fachliche Daten wie ein mitarbeiter UND darf zusaetzlich loeschen/
        # wiederherstellen, ein mandant_admin soll sich diese Berechtigung
        # nicht selbst zuweisen koennen.
        if body.role in _PAPIERKORB_ROLLEN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="mandant_admin darf keine Papierkorb-Accounts anlegen",
            )
        if body.mandant_id != auth.mandant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accounts können nur im eigenen Mandanten angelegt werden",
            )

    if body.role == "custom":
        account_typ = await session.get(AccountTyp, body.account_typ_id)
        if account_typ is None or account_typ.mandant_id != body.mandant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account-Typ nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )

    user = User(
        mandant_id=body.mandant_id,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
        account_typ_id=body.account_typ_id if body.role == "custom" else None,
        name=body.name,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=_integrity_error_detail(exc)
        ) from exc
    await besetzung_pflegen(session, user, neu=True, actor_user_id=auth.user_id)

    await log_action(
        session,
        aktion="user_erstellt",
        mandant_id=user.mandant_id,
        actor_user_id=auth.user_id,
        entity_type="user",
        entity_id=user.id,
        payload={"email": user.email, "role": user.role},
    )
    return await _to_read(session, user)


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    # custom nur fuer das Setzen des Account-Typs mit rechte_verwalten (Eskalationsschutz,
    # siehe _custom_account_typ_pruefen); alle anderen Felder bleiben Admin-Sache.
    dependencies=[Depends(require_roles("super_admin", "mandant_admin", "custom"))],
)
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> UserRead:
    user = await session.get(User, user_id)
    if user is None or ist_anonymisiert(user):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden"
        )

    if auth.role == "custom":
        await _custom_account_typ_pruefen(session, auth, user, body)
    if auth.role in ("mandant_admin", "loesch_operativ"):
        if user.mandant_id != auth.mandant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden"
            )
        if body.role == "super_admin" or user.role == "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nicht berechtigt für super_admin-Accounts",
            )
        if body.role in _PAPIERKORB_ROLLEN or user.role in _PAPIERKORB_ROLLEN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nicht berechtigt für Papierkorb-Accounts",
            )

    changes = body.model_dump(exclude_unset=True, exclude={"password"})
    if changes.get("aktiv") is False or ("role" in changes and changes["role"] != "mandant_admin"):
        await esk.letzten_admin_pruefen(session, user)
    vorher_audit = {"role": user.role, "account_typ_id": user.account_typ_id, "aktiv": user.aktiv}
    # Vor dem Setzen vergleichen: nur ein tatsaechlicher Wechsel entwertet
    # Tokens (Rolle/Account-Typ steckt als Claim im Token, Deaktivierung
    # soll sofort greifen).
    tokens_widerrufen = (
        (changes.get("aktiv") is False and user.aktiv)
        or ("role" in changes and changes["role"] != user.role)
        or ("account_typ_id" in changes and changes["account_typ_id"] != user.account_typ_id)
        or bool(body.password)
    )
    async with esk.verwaltung_bleibt_erhalten(session, user.mandant_id):
        alte_rolle, alter_account_typ_id, war_aktiv = user.role, user.account_typ_id, user.aktiv
        for field, value in changes.items():
            setattr(user, field, value)
        if body.password:
            user.password_hash = hash_password(body.password)
            changes["password"] = "***"
        if user.role == "custom":
            if user.account_typ_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="account_typ_id ist für role='custom' erforderlich",
                )
            account_typ = await session.get(AccountTyp, user.account_typ_id)
            if account_typ is None or account_typ.mandant_id != user.mandant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Account-Typ nicht gefunden oder gehört nicht zum eigenen Mandanten",
                )
        else:
            user.account_typ_id = None
        try:
            await session.flush()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=_integrity_error_detail(exc)
            ) from exc
        await besetzung_pflegen(
            session,
            user,
            alte_rolle=alte_rolle,
            alter_account_typ_id=alter_account_typ_id,
            war_aktiv=war_aktiv,
            actor_user_id=auth.user_id,
        )
    if tokens_widerrufen:
        await widerrufe_tokens(session, user)
    if changes:
        # See mandanten.update_mandant: UPDATE has no implicit RETURNING for
        # server-computed columns, so refresh before the response is built.
        await session.refresh(user)

    if changes:
        await log_action(
            session,
            aktion="user_geaendert",
            mandant_id=user.mandant_id,
            actor_user_id=auth.user_id,
            entity_type="user",
            entity_id=user.id,
            # UUID (account_typ_id) ist nicht JSON-serialisierbar.
            payload=jsonable_encoder(changes),
        )
        if {"role", "account_typ_id", "aktiv"} & changes.keys():
            await log_aenderung(
                session,
                aktion="user_rolle_geaendert",
                mandant_id=user.mandant_id,
                actor_user_id=auth.user_id,
                entity_type="user",
                entity_id=user.id,
                vorher=vorher_audit,
                nachher={"role": user.role, "account_typ_id": user.account_typ_id, "aktiv": user.aktiv},
            )
    return await _to_read(session, user)


@router.post(
    "/{user_id}/abmelden",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("super_admin", "mandant_admin"))],
)
async def user_abmelden_erzwingen(
    user_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Entwertet alle Tokens des Nutzers (z. B. bei verlorenem Geraet),
    ohne den Account zu deaktivieren. Gleiche Rechtegrenzen wie das
    Deaktivieren per PATCH."""
    user = await session.get(User, user_id)
    if user is None or ist_anonymisiert(user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden")

    if auth.role in ("mandant_admin", "loesch_operativ"):
        if user.mandant_id != auth.mandant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden")
        if user.role == "super_admin" or user.role in _PAPIERKORB_ROLLEN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nicht berechtigt für diesen Account",
            )

    await widerrufe_tokens(session, user)
    await log_action(
        session,
        aktion="user_abgemeldet",
        mandant_id=user.mandant_id,
        actor_user_id=auth.user_id,
        entity_type="user",
        entity_id=user.id,
        payload={},
    )


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("super_admin", "mandant_admin"))],
)
async def delete_user(
    user_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    user = await session.get(User, user_id)
    if user is None or ist_anonymisiert(user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden")

    if auth.role in ("mandant_admin", "loesch_operativ"):
        if user.mandant_id != auth.mandant_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden")
        if user.role == "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nicht berechtigt für super_admin-Accounts",
            )
        if user.role in _PAPIERKORB_ROLLEN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nicht berechtigt für Papierkorb-Accounts",
            )

    if user.id == auth.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Der eigene Account kann nicht gelöscht werden"
        )

    if user.role == "mandant_admin":
        # Ein Mandant ohne jeden mandant_admin waere von niemandem mehr
        # verwaltbar -- der letzte muss also erhalten bleiben. Anonymisierte
        # Admins zaehlen nicht mit (Zeile bleibt als Rolle mandant_admin bestehen).
        andere_admins = await session.scalar(
            select(func.count()).select_from(User).where(
                User.mandant_id == user.mandant_id,
                User.role == "mandant_admin",
                User.id != user.id,
                nicht_anonymisiert(),
            )
        )
        if andere_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Der letzte Mandanten-Admin kann nicht gelöscht werden",
            )

    if user.role == "super_admin":
        andere_super_admins = await session.scalar(
            select(func.count()).select_from(User).where(
                User.role == "super_admin", User.id != user.id, nicht_anonymisiert()
            )
        )
        if andere_super_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Der letzte Super-Admin kann nicht gelöscht werden",
            )

    mandant_id = user.mandant_id
    rolle = user.role
    audit_payload = {"role": user.role}
    try:
        # Savepoint, damit ein FK-Verstoss nicht die ganze Request-Transaktion
        # abbricht. Core-DELETE statt session.delete(): der ORM-Zustand bleibt
        # nach dem Rollback unveraendert und wird anschliessend anonymisiert.
        async with session.begin_nested():
            await session.execute(sa_delete(User).where(User.id == user_id))
    except IntegrityError:
        await anonymisiere_user(session, user, auth.user_id)
        # DSGVO: keine alte E-Mail im Audit-Log, nur ID + Rolle + Akteur.
        await log_action(
            session,
            aktion="user_anonymisiert",
            mandant_id=mandant_id,
            actor_user_id=auth.user_id,
            entity_type="user",
            entity_id=user_id,
            payload={"role": rolle},
        )
        return

    await log_action(
        session,
        aktion="user_geloescht",
        mandant_id=mandant_id,
        actor_user_id=auth.user_id,
        entity_type="user",
        entity_id=user_id,
        payload=audit_payload,
    )


@router.patch("/me/bottom-nav", response_model=BottomNavUpdate)
async def update_own_bottom_nav(
    body: BottomNavUpdate, auth: AuthContext = Depends(get_current_user)
) -> BottomNavUpdate:
    # Rein selbstbezogene Praeferenz -- jede Rolle darf sie fuer sich selbst
    # setzen, unabhaengig von mitarbeiterverwaltung-Rechten. Ueber
    # system_session() (analog auth.me), da die Route auch fuer
    # super_admin (mandant_id NULL, ausserhalb jeder RLS-Session) und
    # waehrend Impersonation greifen muss.
    async with system_session() as session:
        user = await session.get(User, auth.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden")
        # Immer vollstaendiger Ersatz beider Listen -- links/rotunde beide
        # None bedeutet "zur Standardauswahl zuruecksetzen" (siehe
        # BottomNavUpdate), sonst wird der komplette neue Stand gespeichert.
        user.bottom_nav_items = (
            None if body.links is None and body.rotunde is None else body.model_dump()
        )
        await session.flush()
    return body


@router.patch("/me/office-nav", response_model=OfficeNavUpdate)
async def update_own_office_nav(
    body: OfficeNavUpdate, auth: AuthContext = Depends(get_current_user)
) -> OfficeNavUpdate:
    # Rein selbstbezogene Praeferenz, analog zu update_own_bottom_nav.
    async with system_session() as session:
        user = await session.get(User, auth.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden")
        user.office_nav_items = body.items
        await session.flush()
    return body
