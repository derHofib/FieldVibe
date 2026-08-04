import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AuthContext,
    get_current_user,
    get_db,
    require_module,
    require_recht,
    require_roles,
)
from app.core.security import hash_password
from app.models.anlage import Anlage
from app.models.kunde import Kunde
from app.models.kunde_zuweisung import KundeZuweisung
from app.models.kundenportal import KundenportalZugang
from app.models.tag import Tag, TagAssignment
from app.models.user import User
from app.models.vorgang import Vorgang
from app.schemas.kunde import KundeCreate, KundeLogoUrl, KundeRead, KundeUpdate
from app.schemas.kunde_zuweisung import KundeZuweisungUpdate
from app.schemas.kundenportal import (
    KundenportalZugangCreate,
    KundenportalZugangRead,
    KundenportalZugangUpdate,
)
from app.schemas.profile import KundeProfil
from app.schemas.user import UserRead
from app.services import papierkorb_service, storage_service
from app.services.numbering_service import next_kundennummer
from app.services.zuweisung_service import assigned_kunde_ids

# super_admin is deliberately excluded: fachliche Daten sind immer
# mandantengebunden, und ein nicht-impersonierender super_admin hat kein
# mandant_id im Token. Zugriff läuft für die Plattform-Rolle ausschließlich
# über "Login als Mandant" (das Token trägt dann role=mandant_admin).
# loesch_operativ (Papierkorb) sieht fachliche Daten wie ein mitarbeiter
# zusaetzlich mit -- siehe app/api/routes/papierkorb.py.
router = APIRouter(
    prefix="/api/kunden",
    tags=["kunden"],
    dependencies=[
        Depends(
            require_roles(
                "mandant_admin", "disponent", "techniker", "controller", "mitarbeiter",
                "loesch_operativ",
            )
        )
    ],
)


@router.get("", response_model=list[KundeRead], dependencies=[Depends(require_recht("kunden", "sehen"))])
async def list_kunden(
    q: str | None = Query(default=None, description="Suche in Name/Kundennummer"),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Kunde]:
    stmt = select(Kunde).where(Kunde.geloescht_am.is_(None)).order_by(Kunde.name)
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
    dependencies=[
        Depends(require_roles("mandant_admin", "disponent", "controller", "mitarbeiter")),
        Depends(require_recht("kunden", "bearbeiten")),
    ],
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
        # Ein Link fuer den gesamten Kunden (nicht pro Ansprechpartner) --
        # jeder Mitarbeiter des Kunden mit eigenem KundenportalZugang meldet
        # sich darueber mit seiner eigenen E-Mail/seinem eigenen Passwort an.
        portal_slug=secrets.token_urlsafe(12),
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


@router.get(
    "/{kunde_id}", response_model=KundeRead, dependencies=[Depends(require_recht("kunden", "sehen"))]
)
async def get_kunde(
    kunde_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Kunde:
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None or kunde.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")
    await _require_kunde_zugriff(session, auth, kunde_id)
    return kunde


@router.get(
    "/{kunde_id}/profil",
    response_model=KundeProfil,
    dependencies=[
        Depends(require_module("kundenverwaltung")),
        Depends(require_recht("kunden", "sehen")),
    ],
)
async def get_kunde_profil(
    kunde_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> KundeProfil:
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None or kunde.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")
    await _require_kunde_zugriff(session, auth, kunde_id)

    anlagen_result = await session.execute(
        select(Anlage)
        .where(Anlage.kunde_id == kunde_id, Anlage.geloescht_am.is_(None))
        .order_by(Anlage.bezeichnung)
    )
    vorgaenge_result = await session.execute(
        select(Vorgang)
        .where(Vorgang.kunde_id == kunde_id, Vorgang.geloescht_am.is_(None))
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
        Depends(require_roles("mandant_admin", "disponent", "controller", "mitarbeiter")),
        Depends(require_module("kundenverwaltung")),
        Depends(require_recht("kunden", "bearbeiten")),
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
        Depends(require_roles("mandant_admin", "disponent", "loesch_operativ")),
        Depends(require_module("kundenverwaltung")),
    ],
)
async def delete_kunde(
    kunde_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    # Papierkorb statt Hard-Delete: verschiebt den Kunden UND alle fachlich
    # abhaengigen Datensaetze (Standorte, Anlagen, Vertraege, Vorgaenge, ...)
    # kaskadierend in den Papierkorb (siehe app/services/papierkorb_service.py).
    # Portal-Zugaenge/Tag-Zuordnungen bleiben unangetastet stehen, da der
    # Kunden-Datensatz selbst nicht mehr geloescht, sondern nur markiert wird.
    kunde = await papierkorb_service.soft_delete(
        session, entity_typ="kunde", entity_id=kunde_id, actor_user_id=auth.user_id
    )
    if kunde is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")


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


@router.post(
    "/{kunde_id}/portal-zugaenge",
    response_model=KundenportalZugangRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "disponent")),
        Depends(require_module("kundenportal")),
    ],
)
async def create_portal_zugang(
    kunde_id: UUID,
    body: KundenportalZugangCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> KundenportalZugang:
    if await session.get(Kunde, kunde_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")
    if len(body.password) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Passwort muss mindestens 10 Zeichen haben"
        )

    zugang = KundenportalZugang(
        mandant_id=auth.mandant_id,
        kunde_id=kunde_id,
        email=body.email,
        password_hash=hash_password(body.password),
        name=body.name,
    )
    session.add(zugang)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="E-Mail wird bereits verwendet"
        ) from exc
    return zugang


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


_LOGO_MAX_BYTES = 3 * 1024 * 1024


@router.post(
    "/{kunde_id}/logo",
    response_model=KundeRead,
    dependencies=[
        Depends(require_roles("mandant_admin")),
        Depends(require_module("kundenportal")),
    ],
)
async def upload_kunde_logo(
    kunde_id: UUID,
    file: UploadFile,
    session: AsyncSession = Depends(get_db),
) -> Kunde:
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Nur Bilddateien werden unterstützt"
        )

    data = await file.read()
    if len(data) > _LOGO_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Datei zu groß (max. 3 MB)"
        )

    alter_key = kunde.logo_object_key
    key = storage_service.new_kunde_logo_key(kunde_id, file.filename or "logo.png")
    await storage_service.upload_bytes(key, data, file.content_type)
    kunde.logo_object_key = key
    await session.flush()
    await session.refresh(kunde)

    if alter_key is not None:
        await storage_service.delete_object(alter_key)
    return kunde


@router.delete(
    "/{kunde_id}/logo",
    response_model=KundeRead,
    dependencies=[
        Depends(require_roles("mandant_admin")),
        Depends(require_module("kundenportal")),
    ],
)
async def remove_kunde_logo(kunde_id: UUID, session: AsyncSession = Depends(get_db)) -> Kunde:
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")

    alter_key = kunde.logo_object_key
    kunde.logo_object_key = None
    await session.flush()
    await session.refresh(kunde)

    if alter_key is not None:
        await storage_service.delete_object(alter_key)
    return kunde


@router.get(
    "/{kunde_id}/logo-url",
    response_model=KundeLogoUrl,
    dependencies=[Depends(require_recht("kunden", "sehen"))],
)
async def get_kunde_logo_url(
    kunde_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> KundeLogoUrl:
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")
    await _require_kunde_zugriff(session, auth, kunde_id)

    if kunde.logo_object_key is None:
        return KundeLogoUrl(url=None)
    return KundeLogoUrl(url=storage_service.presigned_get_url(kunde.logo_object_key))
