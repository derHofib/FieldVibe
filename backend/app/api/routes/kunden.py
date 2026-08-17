import secrets
from datetime import UTC, datetime
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
from app.models.angebot import Angebot
from app.models.anlage import Anlage
from app.models.einladung import Einladung
from app.models.email_log import EmailLog
from app.models.kunde import Kunde
from app.models.kunde_zuweisung import KundeZuweisung
from app.models.kundenportal import KundenportalZugang
from app.models.mandant import Mandant
from app.models.rechnung import Rechnung
from app.models.standort import Standort
from app.models.tag import Tag, TagAssignment
from app.models.user import User
from app.models.vertrag import Vertrag
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.anlage import AnlageRead
from app.schemas.datenexport import KundeDatenexport, VorgangMitEreignissen
from app.schemas.einladung import EinladungRead, KundeEinladungCreate
from app.schemas.email import EmailLogRead, EmailSenden
from app.schemas.kunde import KundeCreate, KundeLogoUrl, KundeRead, KundeUpdate
from app.schemas.kunde_zuweisung import KundeZuweisungUpdate
from app.schemas.kundenportal import KundenportalZugangRead, KundenportalZugangUpdate
from app.schemas.profile import KundeProfil
from app.schemas.standort import StandortRead
from app.schemas.user import UserRead
from app.schemas.vertrag import VertragRead
from app.schemas.vorgang import VorgangRead
from app.schemas.vorgang_event import VorgangEventRead
from app.services import angebot_service, papierkorb_service, rechnung_service, storage_service
from app.services.einladung_service import create_einladung, to_read_model, versende_einladung
from app.services.email_service import send_email_and_log
from app.services.numbering_service import next_kundennummer
from app.services.rechte_service import ist_auf_zugewiesene_kunden_beschraenkt
from app.services.zuweisung_service import assigned_kunde_ids, technik_user_ids

# super_admin is deliberately excluded: fachliche Daten sind immer
# mandantengebunden, und ein nicht-impersonierender super_admin hat kein
# mandant_id im Token. Zugriff läuft für die Plattform-Rolle ausschließlich
# über "Login als Mandant" (das Token trägt dann role=mandant_admin).
# loesch_operativ hat ueberall dieselben Rechte wie mandant_admin (siehe
# app/api/deps.py:require_roles()) und braucht daher wie dieser Zugriff auf
# diesen Router.
router = APIRouter(
    prefix="/api/kunden",
    tags=["kunden"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ"))
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
    if await ist_auf_zugewiesene_kunden_beschraenkt(
        session, role=auth.role, account_typ_id=auth.account_typ_id
    ):
        stmt = stmt.where(Kunde.id.in_(await assigned_kunde_ids(session, auth.user_id)))
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "",
    response_model=KundeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("kunden", "erstellen")),
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
        ust_idnr=body.ust_idnr,
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
    beschraenkt = await ist_auf_zugewiesene_kunden_beschraenkt(
        session, role=auth.role, account_typ_id=auth.account_typ_id
    )
    if beschraenkt and kunde_id not in await assigned_kunde_ids(session, auth.user_id):
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
    "/{kunde_id}/emails",
    response_model=list[EmailLogRead],
    dependencies=[Depends(require_recht("kunden", "sehen"))],
)
async def list_kunde_emails(
    kunde_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[EmailLog]:
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None or kunde.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")
    await _require_kunde_zugriff(session, auth, kunde_id)
    result = await session.execute(
        select(EmailLog)
        .where(EmailLog.entity_type == "kunde", EmailLog.entity_id == kunde_id)
        .order_by(EmailLog.created_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/{kunde_id}/emails",
    response_model=EmailLogRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_recht("kunden", "bearbeiten"))],
)
async def send_kunde_email(
    kunde_id: UUID,
    body: EmailSenden,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> EmailLog:
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None or kunde.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")
    await _require_kunde_zugriff(session, auth, kunde_id)

    log = await send_email_and_log(
        session,
        auth.mandant_id,
        entity_type="kunde",
        entity_id=kunde_id,
        to=body.empfaenger,
        subject=body.betreff,
        body=body.inhalt,
        gesendet_von=auth.user_id,
    )
    return log


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
    "/{kunde_id}/datenexport",
    response_model=KundeDatenexport,
    dependencies=[Depends(require_recht("kunden", "sehen"))],
)
async def get_kunde_datenexport(
    kunde_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> KundeDatenexport:
    """Alle personenbezogenen Daten zu diesem Kunden als maschinenlesbare
    Struktur -- fuer Auskunftsersuchen (Art. 15 DSGVO) und Datenuebertragbarkeit
    (Art. 20 DSGVO). Siehe app/schemas/datenexport.py fuer den bewussten
    Ausschluss von Passwort-Hashes/Binaerdaten."""
    kunde = await session.get(Kunde, kunde_id)
    if kunde is None or kunde.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kunde nicht gefunden")
    await _require_kunde_zugriff(session, auth, kunde_id)

    standorte = (
        await session.execute(
            select(Standort).where(Standort.kunde_id == kunde_id, Standort.geloescht_am.is_(None))
        )
    ).scalars().all()
    anlagen = (
        await session.execute(
            select(Anlage).where(Anlage.kunde_id == kunde_id, Anlage.geloescht_am.is_(None))
        )
    ).scalars().all()
    vertraege = (
        await session.execute(
            select(Vertrag).where(Vertrag.kunde_id == kunde_id, Vertrag.geloescht_am.is_(None))
        )
    ).scalars().all()
    vorgaenge = (
        await session.execute(
            select(Vorgang)
            .where(Vorgang.kunde_id == kunde_id, Vorgang.geloescht_am.is_(None))
            .order_by(Vorgang.created_at)
        )
    ).scalars().all()
    events_by_vorgang: dict[UUID, list[VorgangEvent]] = {v.id: [] for v in vorgaenge}
    if vorgaenge:
        events = (
            await session.execute(
                select(VorgangEvent)
                .where(VorgangEvent.vorgang_id.in_(events_by_vorgang.keys()))
                .order_by(VorgangEvent.created_at)
            )
        ).scalars().all()
        for event in events:
            events_by_vorgang[event.vorgang_id].append(event)
    angebote = (
        await session.execute(
            select(Angebot).where(Angebot.kunde_id == kunde_id, Angebot.geloescht_am.is_(None))
        )
    ).scalars().all()
    rechnungen = (
        await session.execute(
            select(Rechnung).where(Rechnung.kunde_id == kunde_id, Rechnung.geloescht_am.is_(None))
        )
    ).scalars().all()
    emails = (
        await session.execute(
            select(EmailLog)
            .where(EmailLog.entity_type == "kunde", EmailLog.entity_id == kunde_id)
            .order_by(EmailLog.created_at)
        )
    ).scalars().all()
    portal_zugaenge = (
        await session.execute(select(KundenportalZugang).where(KundenportalZugang.kunde_id == kunde_id))
    ).scalars().all()
    tags = (
        await session.execute(
            select(Tag.label)
            .join(TagAssignment, TagAssignment.tag_id == Tag.id)
            .where(TagAssignment.entity_type == "kunde", TagAssignment.entity_id == kunde_id)
        )
    ).scalars().all()

    return KundeDatenexport(
        exportiert_am=datetime.now(UTC),
        kunde=KundeRead.model_validate(kunde),
        standorte=[StandortRead.model_validate(s) for s in standorte],
        anlagen=[AnlageRead.model_validate(a) for a in anlagen],
        vertraege=[VertragRead.model_validate(v) for v in vertraege],
        vorgaenge=[
            VorgangMitEreignissen(
                **VorgangRead.model_validate(v).model_dump(),
                ereignisse=[VorgangEventRead.model_validate(e) for e in events_by_vorgang[v.id]],
            )
            for v in vorgaenge
        ],
        angebote=[await angebot_service.to_read_model(session, a) for a in angebote],
        rechnungen=[await rechnung_service.to_read_model(session, r) for r in rechnungen],
        emails=[EmailLogRead.model_validate(e) for e in emails],
        kundenportal_zugaenge=[KundenportalZugangRead.model_validate(z) for z in portal_zugaenge],
        tags=list(tags),
    )


@router.get(
    "/{kunde_id}/techniker",
    response_model=list[UserRead],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("kunden", "sehen")),
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
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("kunden", "bearbeiten")),
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
        gueltige_ids = await technik_user_ids(session, auth.mandant_id) & user_ids
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
        Depends(require_roles("mandant_admin", "custom")),
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
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("kunden", "loeschen")),
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
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("kunden", "bearbeiten")),
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
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("kunden", "bearbeiten")),
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
