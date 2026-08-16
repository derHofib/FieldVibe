from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_module, require_roles
from app.core.security import hash_password
from app.models.anlage import Anlage
from app.models.einladung import Einladung
from app.models.kunde import Kunde
from app.models.kunde_zuweisung import KundeZuweisung
from app.models.kundenportal import KundenportalZugang
from app.models.mandant import Mandant
from app.models.tag import Tag, TagAssignment
from app.models.user import User
from app.models.vorgang import Vorgang
from app.schemas.einladung import EinladungRead, KundeEinladungCreate
from app.schemas.kunde import KundeCreate, KundeRead, KundeUpdate
from app.schemas.kunde_zuweisung import KundeZuweisungUpdate
from app.schemas.kundenportal import KundenportalZugangRead, KundenportalZugangUpdate
from app.schemas.profile import KundeProfil
from app.schemas.user import UserRead
from app.services.einladung_service import create_einladung, to_read_model, versende_einladung
from app.services.numbering_service import next_kundennummer
from app.services.zuweisung_service import assigned_kunde_ids

# super_admin is deliberately excluded: fachliche Daten sind immer
# mandantengebunden, und ein nicht-impersonierender super_admin hat kein
# mandant_id im Token. Zugriff läuft für die Plattform-Rolle ausschließlich
# über "Login als Mandant" (das Token trägt dann role=mandant_admin).
router = APIRouter(
    prefix="/api/kunden",
    tags=["kunden"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)


@router.get("", response_model=list[KundeRead])
async def list_kunden(
    q: str | None = Query(default=None, description="Suche in Name/Kundennummer"),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Kunde]:
    stmt = select(Kunde).order_by(Kunde.name)
    if q:
        stmt = stmt.where(Kunde.name.ilike(f"%{q}%"))
    if auth.role == "techniker":
        stmt = stmt.where(Kunde.id.in_(await assigned_kunde_ids(session, auth.user_id)))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "",
    response_model=KundeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("mandant_admin", "disponent"))],
)
async def create_kunde(
    body: KundeCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Kunde:
    kundennummer = body.kundennummer or await next_kundennummer(session, auth.mandant_id)
    kunde = Kunde(
        mandant_id=auth.mandant_id,
        kundennummer=kundennummer,
        name=body.name,
        typ=body.typ,
        ansprechpartner=[a.model_dump(mode="json") for a in body.ansprechpartner],
        adresse=body.adresse,
        notiz=body.notiz,
    )
    session.add(kunde)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Kundennummer bereits vergeben"
        ) from exc
    return kunde


async def _require_kunde_zugriff(
    session: AsyncSession, auth: AuthContext, kunde_id: UUID
) -> None:
    if auth.role == "techniker" and kunde_id not in await assigned_kunde_ids(
        session, auth.user_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")


@router.get("/{kunde_id}", response_model=KundeRead)
async def get_kunde(
    kunde_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Kunde:
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")
    await _require_kunde_zugriff(session, auth, kunde_id)
    return kunde


@router.get(
    "/{kunde_id}/profil",
    response_model=KundeProfil,
    dependencies=[Depends(require_module("kundenverwaltung"))],
)
async def get_kunde_profil(
    kunde_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> KundeProfil:
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")
    await _require_kunde_zugriff(session, auth, kunde_id)

    anlagen_result = await session.execute(
        select(Anlage).where(Anlage.kunde_id == kunde_id).order_by(Anlage.bezeichnung)
    )
    vorgaenge_result = await session.execute(
        select(Vorgang)
        .where(Vorgang.kunde_id == kunde_id)
        .order_by(Vorgang.last_activity_at.desc())
        .limit(50)
    )
    tags_result = await session.execute(
        select(Tag)
        .join(TagAssignment, TagAssignment.tag_id == Tag.id)
        .where(TagAssignment.entity_type == "kunde", TagAssignment.entity_id == kunde_id)
    )
    techniker_result = await session.execute(
        select(User)
        .join(KundeZuweisung, KundeZuweisung.user_id == User.id)
        .where(KundeZuweisung.kunde_id == kunde_id)
        .order_by(User.name)
    )

    return KundeProfil(
        **KundeRead.model_validate(kunde).model_dump(),
        anlagen=list(anlagen_result.scalars().all()),
        vorgaenge=list(vorgaenge_result.scalars().all()),
        tags=list(tags_result.scalars().all()),
        techniker=list(techniker_result.scalars().all()),
    )


@router.get(
    "/{kunde_id}/techniker",
    response_model=list[UserRead],
    dependencies=[
        Depends(require_roles("mandant_admin", "disponent")),
        Depends(require_module("kundenverwaltung")),
    ],
)
async def list_kunde_techniker(
    kunde_id: UUID, session: AsyncSession = Depends(get_db)
) -> list[User]:
    if await session.get(Kunde, kunde_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")
    result = await session.execute(
        select(User)
        .join(KundeZuweisung, KundeZuweisung.user_id == User.id)
        .where(KundeZuweisung.kunde_id == kunde_id)
        .order_by(User.name)
    )
    return list(result.scalars().all())


@router.put(
    "/{kunde_id}/techniker",
    response_model=list[UserRead],
    dependencies=[
        Depends(require_roles("mandant_admin", "disponent")),
        Depends(require_module("kundenverwaltung")),
    ],
)
async def set_kunde_techniker(
    kunde_id: UUID,
    body: KundeZuweisungUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[User]:
    if await session.get(Kunde, kunde_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")

    user_ids = set(body.user_ids)
    if user_ids:
        gueltige_result = await session.execute(
            select(User.id).where(User.id.in_(user_ids), User.role == "techniker")
        )
        gueltige_ids = set(gueltige_result.scalars().all())
        if gueltige_ids != user_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mindestens ein user_id ist ungültig oder kein Techniker dieses Mandanten",
            )

    bestehende_result = await session.execute(
        select(KundeZuweisung).where(KundeZuweisung.kunde_id == kunde_id)
    )
    bestehende = {z.user_id: z for z in bestehende_result.scalars().all()}

    for user_id, zuweisung in bestehende.items():
        if user_id not in user_ids:
            await session.delete(zuweisung)
    for user_id in user_ids - bestehende.keys():
        session.add(
            KundeZuweisung(mandant_id=auth.mandant_id, kunde_id=kunde_id, user_id=user_id)
        )
    await session.flush()

    result = await session.execute(
        select(User)
        .join(KundeZuweisung, KundeZuweisung.user_id == User.id)
        .where(KundeZuweisung.kunde_id == kunde_id)
        .order_by(User.name)
    )
    return list(result.scalars().all())


@router.patch(
    "/{kunde_id}",
    response_model=KundeRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "disponent")),
        Depends(require_module("kundenverwaltung")),
    ],
)
async def update_kunde(
    kunde_id: UUID, body: KundeUpdate, session: AsyncSession = Depends(get_db)
) -> Kunde:
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")

    # mode="json" statt des Standard-model_dump(): ansprechpartner enthaelt
    # verschachtelte AnsprechpartnerEintrag-Objekte, deren id ein UUID-Objekt
    # ist -- die JSONB-Spalte braucht dafuer JSON-taugliche Werte (str statt
    # UUID), sonst schlaegt das Schreiben in die Datenbank fehl.
    changes = body.model_dump(exclude_unset=True, mode="json")
    for field, value in changes.items():
        setattr(kunde, field, value)
    await session.flush()
    if changes:
        await session.refresh(kunde)
    return kunde


@router.delete(
    "/{kunde_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_roles("mandant_admin", "disponent")),
        Depends(require_module("kundenverwaltung")),
    ],
)
async def delete_kunde(kunde_id: UUID, session: AsyncSession = Depends(get_db)) -> None:
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")

    # Portal-Zugaenge (Login-Credentials) und Tag-Zuordnungen (entity_id ist
    # polymorph, hat also keine echte FK zu kunden.id) sind reine Anhaengsel
    # des Kunden, keine eigenstaendigen Geschaeftsvorfaelle -- die raeumen
    # wir mit auf. kunde_zuweisungen loescht sich per ondelete=CASCADE
    # bereits selbst. Alles mit echtem fachlichem Gewicht (Anlagen, Vorgaenge,
    # Vertraege, Angebote, Rechnungen, Dauerauftraege) blockt die eigentliche
    # Loeschung unten ueber den FK-Constraint.
    await session.execute(delete(KundenportalZugang).where(KundenportalZugang.kunde_id == kunde_id))
    await session.execute(
        delete(TagAssignment).where(
            TagAssignment.entity_type == "kunde", TagAssignment.entity_id == kunde_id
        )
    )

    try:
        await session.delete(kunde)
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Kunde kann nicht gelöscht werden, da noch Daten verknüpft sind "
                "(z.B. Anlagen, Vorgänge, Verträge, Angebote, Rechnungen)."
            ),
        ) from exc


@router.get(
    "/{kunde_id}/portal-zugaenge",
    response_model=list[KundenportalZugangRead],
    dependencies=[Depends(require_module("kundenportal"))],
)
async def list_portal_zugaenge(
    kunde_id: UUID, session: AsyncSession = Depends(get_db)
) -> list[KundenportalZugang]:
    if await session.get(Kunde, kunde_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")
    result = await session.execute(
        select(KundenportalZugang).where(KundenportalZugang.kunde_id == kunde_id)
    )
    return list(result.scalars().all())


@router.get(
    "/{kunde_id}/einladungen",
    response_model=list[EinladungRead],
    dependencies=[
        Depends(require_roles("mandant_admin", "disponent")),
        Depends(require_module("kundenportal")),
    ],
)
async def list_kunde_einladungen(
    kunde_id: UUID, session: AsyncSession = Depends(get_db)
) -> list[EinladungRead]:
    if await session.get(Kunde, kunde_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")
    result = await session.execute(
        select(Einladung)
        .where(Einladung.art == "kunde", Einladung.kunde_id == kunde_id)
        .order_by(Einladung.created_at.desc())
    )
    return [EinladungRead(**to_read_model(e)) for e in result.scalars().all()]


@router.post(
    "/{kunde_id}/einladungen",
    response_model=EinladungRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "disponent")),
        Depends(require_module("kundenportal")),
    ],
)
async def kunde_einladen(
    kunde_id: UUID,
    body: KundeEinladungCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> EinladungRead:
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")

    einladender = await session.get(User, auth.user_id)
    einladung = await create_einladung(
        session,
        mandant_id=auth.mandant_id,
        email=body.email,
        art="kunde",
        kunde_id=kunde_id,
        eingeladen_von=auth.user_id,
    )
    link = await versende_einladung(
        session,
        einladung,
        absender_name=einladender.name if einladender else kunde.name,
        absender_rolle=einladender.role if einladender else None,
    )
    return EinladungRead(**to_read_model(einladung, registrierungslink=link))


@router.post(
    "/{kunde_id}/einladungen/{einladung_id}/erneut-senden",
    response_model=EinladungRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "disponent")),
        Depends(require_module("kundenportal")),
    ],
)
async def kunde_einladung_erneut_senden(
    kunde_id: UUID,
    einladung_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> EinladungRead:
    einladung = await session.get(Einladung, einladung_id)
    if einladung is None or einladung.art != "kunde" or einladung.kunde_id != kunde_id or einladung.status != "offen":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Einladung nicht gefunden")

    einladender = await session.get(User, auth.user_id)
    link = await versende_einladung(
        session,
        einladung,
        absender_name=einladender.name if einladender else "",
        absender_rolle=einladender.role if einladender else None,
    )
    return EinladungRead(**to_read_model(einladung, registrierungslink=link))


@router.delete(
    "/{kunde_id}/einladungen/{einladung_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_roles("mandant_admin", "disponent")),
        Depends(require_module("kundenportal")),
    ],
)
async def kunde_einladung_widerrufen(
    kunde_id: UUID, einladung_id: UUID, session: AsyncSession = Depends(get_db)
) -> None:
    einladung = await session.get(Einladung, einladung_id)
    if einladung is None or einladung.art != "kunde" or einladung.kunde_id != kunde_id or einladung.status != "offen":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Einladung nicht gefunden")
    einladung.status = "widerrufen"
    await session.flush()


@router.patch(
    "/{kunde_id}/portal-zugaenge/{zugang_id}",
    response_model=KundenportalZugangRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "disponent")),
        Depends(require_module("kundenportal")),
    ],
)
async def update_portal_zugang(
    kunde_id: UUID,
    zugang_id: UUID,
    body: KundenportalZugangUpdate,
    session: AsyncSession = Depends(get_db),
) -> KundenportalZugang:
    zugang = await session.get(KundenportalZugang, zugang_id)
    if zugang is None or zugang.kunde_id != kunde_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zugang nicht gefunden")

    changes = body.model_dump(exclude_unset=True, exclude={"password"})
    for field, value in changes.items():
        setattr(zugang, field, value)
    if body.password is not None:
        if len(body.password) < 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwort muss mindestens 10 Zeichen haben",
            )
        zugang.password_hash = hash_password(body.password)
        changes["password_hash"] = zugang.password_hash

    await session.flush()
    if changes:
        await session.refresh(zugang)
    return zugang
