from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
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
from app.core.config import get_settings
from app.models.anlage import Anlage
from app.models.email_log import EmailLog
from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.partner import Partner
from app.models.standort import Standort
from app.models.user import User
from app.models.vertrag import Vertrag
from app.models.vorgang import Vorgang
from app.models.vorgang_anlage import VorgangAnlage
from app.models.vorgang_event import VorgangEvent
from app.schemas.anlage import AnlageRead
from app.schemas.email import EmailLogRead, EmailSenden
from app.schemas.partner import VorgangPartnerZuweisung, VorgangPartnerZuweisungResponse
from app.schemas.vorgang import (
    VorgangAnlagenHinzufuegen,
    VorgangCreate,
    VorgangFolgeAuftragErstellen,
    VorgangRead,
    VorgangUpdate,
)
from app.services import papierkorb_service
from app.services.audit_service import log_action
from app.services.csv_service import csv_response
from app.services.email_service import send_email_and_log
from app.services.event_bus import event_bus
from app.services.formular_service import offene_pflichtformulare
from app.services.numbering_service import next_vorgangsnummer
from app.services.partner_service import partner_hat_gueltige_freistellungsbescheinigung
from app.services.rechte_service import (
    darf_vorgang_selbst_uebernehmen,
    ist_auf_zugewiesene_kunden_beschraenkt,
)
from app.services.vorgang_completion_service import (
    VORGANG_STATUS_GESCHLOSSEN,
    close_vorgang,
    create_folge_vorgang,
)
from app.services.zuweisung_service import assigned_kunde_ids


async def _mit_zugewiesenem_namen(session: AsyncSession, vorgang: Vorgang) -> Vorgang:
    # Kein echtes Feld auf Vorgang -- nur transient fuer diese eine Antwort
    # gesetzt, siehe VorgangRead.zugewiesener_name.
    if vorgang.zugewiesener_user_id is not None:
        zugewiesener = await session.get(User, vorgang.zugewiesener_user_id)
        vorgang.zugewiesener_name = zugewiesener.name if zugewiesener else None
    return vorgang

router = APIRouter(
    prefix="/api/vorgaenge",
    tags=["vorgaenge"],
    dependencies=[Depends(require_roles("mandant_admin", "custom", "loesch_operativ"))],
)


@router.get("", response_model=list[VorgangRead], dependencies=[Depends(require_recht("vorgaenge", "sehen"))])
async def list_vorgaenge(
    status_filter: str | None = Query(default=None, alias="status"),
    kunde_id: UUID | None = Query(default=None),
    anlage_id: UUID | None = Query(default=None),
    leistungstyp: str | None = Query(default=None),
    abrechnungsart: str | None = Query(default=None),
    standort_id: UUID | None = Query(default=None),
    parent_vorgang_id: UUID | None = Query(default=None),
    partner_id: UUID | None = Query(default=None),
    faellig_von: date | None = Query(default=None),
    faellig_bis: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Vorgang]:
    stmt = (
        select(Vorgang)
        .where(Vorgang.geloescht_am.is_(None))
        .order_by(Vorgang.last_activity_at.desc(), Vorgang.id.desc())
        .limit(limit)
    )
    if status_filter:
        stmt = stmt.where(Vorgang.status == status_filter)
    if kunde_id:
        stmt = stmt.where(Vorgang.kunde_id == kunde_id)
    if anlage_id:
        stmt = stmt.where(Vorgang.anlage_id == anlage_id)
    if standort_id:
        stmt = stmt.where(Vorgang.standort_id == standort_id)
    if parent_vorgang_id:
        stmt = stmt.where(Vorgang.parent_vorgang_id == parent_vorgang_id)
    if partner_id:
        stmt = stmt.where(Vorgang.partner_id == partner_id)
    if leistungstyp:
        stmt = stmt.where(Vorgang.leistungstyp == leistungstyp)
    if abrechnungsart:
        stmt = stmt.where(Vorgang.abrechnungsart == abrechnungsart)
    if faellig_von:
        stmt = stmt.where(
            Vorgang.faelligkeit_am >= datetime.combine(faellig_von, datetime.min.time(), tzinfo=timezone.utc)
        )
    if faellig_bis:
        stmt = stmt.where(
            Vorgang.faelligkeit_am
            < datetime.combine(faellig_bis + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        )
    if await ist_auf_zugewiesene_kunden_beschraenkt(
        session, role=auth.role, account_typ_id=auth.account_typ_id
    ):
        stmt = stmt.where(Vorgang.kunde_id.in_(await assigned_kunde_ids(session, auth.user_id)))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _validate_anlage_fuer_kunde(
    session: AsyncSession, anlage_id: UUID, kunde_id: UUID
) -> None:
    anlage = await session.get(Anlage, anlage_id)
    if anlage is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anlage nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if anlage.kunde_id != kunde_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anlage gehört nicht zum angegebenen Kunden",
        )
    if not anlage.aktiv:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anlage ist inaktiv und steht für neue Vorgänge nicht zur Auswahl",
        )


async def _validate_references(
    session: AsyncSession, auth: AuthContext, body: VorgangCreate
) -> None:
    kunde = await session.get(Kunde, body.kunde_id)
    if kunde is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kunde nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if await ist_auf_zugewiesene_kunden_beschraenkt(
        session, role=auth.role, account_typ_id=auth.account_typ_id
    ) and body.kunde_id not in await assigned_kunde_ids(session, auth.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dieser Kunde ist dir nicht zugewiesen",
        )
    if body.anlage_id is not None:
        await _validate_anlage_fuer_kunde(session, body.anlage_id, body.kunde_id)
    for weitere_id in body.weitere_anlage_ids:
        await _validate_anlage_fuer_kunde(session, weitere_id, body.kunde_id)
    if body.standort_id is not None:
        standort = await session.get(Standort, body.standort_id)
        if standort is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Standort nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
        if standort.kunde_id != body.kunde_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Standort gehört nicht zum angegebenen Kunden",
            )
        if not standort.aktiv:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Standort ist inaktiv und steht für neue Vorgänge nicht zur Auswahl",
            )
    if body.vertrag_id is not None:
        vertrag = await session.get(Vertrag, body.vertrag_id)
        if vertrag is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vertrag nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
        if vertrag.kunde_id != body.kunde_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vertrag gehört nicht zum angegebenen Kunden",
            )
    if body.parent_vorgang_id is not None and await session.get(Vorgang, body.parent_vorgang_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Übergeordneter Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )


@router.post(
    "",
    response_model=VorgangRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("vorgaenge", "erstellen")),
    ],
)
async def create_vorgang(
    body: VorgangCreate,
    response: Response,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Vorgang:
    if body.client_uuid is not None:
        # Checked up front statt als IntegrityError abgefangen: ein
        # Sync-Retry aus der Offline-Outbox (App wurde waehrend des Syncs
        # beendet, oder eine Antwort ging verloren, obwohl der Request
        # serverseitig ankam) soll denselben Vorgang zurueckgeben statt
        # einen zweiten anzulegen -- dasselbe Muster wie bei
        # VorgangEvent.client_uuid (vorgang_events.py).
        existing = await session.execute(
            select(Vorgang).where(Vorgang.client_uuid == body.client_uuid)
        )
        existing_vorgang = existing.scalar_one_or_none()
        if existing_vorgang is not None:
            response.status_code = status.HTTP_200_OK
            return existing_vorgang

    await _validate_references(session, auth, body)

    vorgangsnummer = body.vorgangsnummer or await next_vorgangsnummer(session, auth.mandant_id)
    vorgang = Vorgang(
        mandant_id=auth.mandant_id,
        vorgangsnummer=vorgangsnummer,
        kunde_id=body.kunde_id,
        anlage_id=body.anlage_id,
        standort_id=body.standort_id,
        vertrag_id=body.vertrag_id,
        parent_vorgang_id=body.parent_vorgang_id,
        titel=body.titel,
        beschreibung=body.beschreibung,
        abrechnungsart=body.abrechnungsart,
        leistungstyp=body.leistungstyp,
        prioritaet=body.prioritaet,
        faelligkeit_am=body.faelligkeit_am,
        adresse=body.adresse,
        client_uuid=body.client_uuid,
        erstellt_von=auth.user_id,
    )
    session.add(vorgang)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Vorgangsnummer bereits vergeben"
        ) from exc

    # Dubletten zur Haupt-Anlage vermeiden (z.B. wenn dieselbe Anlage sowohl
    # als anlage_id als auch in der Standort-Checkliste ausgewaehlt wurde).
    for weitere_id in set(body.weitere_anlage_ids) - {body.anlage_id}:
        session.add(VorgangAnlage(mandant_id=auth.mandant_id, vorgang_id=vorgang.id, anlage_id=weitere_id))

    session.add(
        VorgangEvent(
            mandant_id=auth.mandant_id,
            vorgang_id=vorgang.id,
            event_type="system",
            author_user_id=auth.user_id,
            is_system=True,
            body="Vorgang angelegt",
            payload={"status": vorgang.status},
        )
    )
    await session.flush()
    await session.refresh(vorgang)

    await event_bus.publish(
        auth.mandant_id, "feed_update", {"vorgang_id": str(vorgang.id), "reason": "erstellt"}
    )
    return vorgang


async def _require_vorgang_zugriff(
    session: AsyncSession, auth: AuthContext, vorgang: Vorgang
) -> None:
    beschraenkt = await ist_auf_zugewiesene_kunden_beschraenkt(
        session, role=auth.role, account_typ_id=auth.account_typ_id
    )
    if beschraenkt and vorgang.kunde_id not in await assigned_kunde_ids(session, auth.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")


@router.get(
    "/export/csv",
    dependencies=[
        Depends(require_module("statistik")),
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("vorgaenge", "sehen")),
    ],
)
async def export_vorgaenge_csv(
    status_filter: str | None = Query(default=None, alias="status"),
    kunde_id: UUID | None = Query(default=None),
    von: date | None = Query(default=None),
    bis: date | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    stmt = select(Vorgang).order_by(Vorgang.created_at.asc())
    if status_filter:
        stmt = stmt.where(Vorgang.status == status_filter)
    if kunde_id:
        stmt = stmt.where(Vorgang.kunde_id == kunde_id)
    if von:
        stmt = stmt.where(Vorgang.created_at >= datetime.combine(von, datetime.min.time(), tzinfo=timezone.utc))
    if bis:
        stmt = stmt.where(
            Vorgang.created_at
            < datetime.combine(bis + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        )
    vorgaenge = list((await session.execute(stmt)).scalars().all())

    kunden_by_id: dict[UUID, Kunde | None] = {}
    anlagen_by_id: dict[UUID, Anlage | None] = {}
    rows = []
    for v in vorgaenge:
        if v.kunde_id not in kunden_by_id:
            kunden_by_id[v.kunde_id] = await session.get(Kunde, v.kunde_id)
        kunde = kunden_by_id[v.kunde_id]
        anlage = None
        if v.anlage_id is not None:
            if v.anlage_id not in anlagen_by_id:
                anlagen_by_id[v.anlage_id] = await session.get(Anlage, v.anlage_id)
            anlage = anlagen_by_id[v.anlage_id]
        rows.append(
            [
                v.vorgangsnummer,
                v.titel,
                kunde.name if kunde else "",
                anlage.bezeichnung if anlage else "",
                v.status,
                v.abrechnungsart,
                v.leistungstyp,
                v.created_at.strftime("%d.%m.%Y %H:%M"),
                v.abgeschlossen_am.strftime("%d.%m.%Y %H:%M") if v.abgeschlossen_am else "",
            ]
        )

    return csv_response(
        ["Vorgangsnummer", "Titel", "Kunde", "Anlage", "Status", "Abrechnungsart", "Leistungstyp", "Erstellt am", "Abgeschlossen am"],
        rows,
        "Vorgaenge.csv",
    )


@router.get(
    "/{vorgang_id}",
    response_model=VorgangRead,
    dependencies=[Depends(require_recht("vorgaenge", "sehen"))],
)
async def get_vorgang(
    vorgang_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Vorgang:
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None or vorgang.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
    await _require_vorgang_zugriff(session, auth, vorgang)
    return await _mit_zugewiesenem_namen(session, vorgang)


@router.get("/{vorgang_id}/anlagen", response_model=list[AnlageRead])
async def list_vorgang_anlagen(
    vorgang_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Anlage]:
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None or vorgang.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
    await _require_vorgang_zugriff(session, auth, vorgang)
    result = await session.execute(
        select(Anlage)
        .join(VorgangAnlage, VorgangAnlage.anlage_id == Anlage.id)
        .where(VorgangAnlage.vorgang_id == vorgang_id, Anlage.geloescht_am.is_(None))
        .order_by(Anlage.bezeichnung)
    )
    return list(result.scalars().all())


@router.post(
    "/{vorgang_id}/anlagen",
    response_model=list[AnlageRead],
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("vorgaenge", "bearbeiten")),
    ],
)
async def add_vorgang_anlagen(
    vorgang_id: UUID,
    body: VorgangAnlagenHinzufuegen,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Anlage]:
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None or vorgang.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")

    bestehende = await session.execute(
        select(VorgangAnlage.anlage_id).where(VorgangAnlage.vorgang_id == vorgang_id)
    )
    bereits_zugeordnet = set(bestehende.scalars().all()) | {vorgang.anlage_id}

    for anlage_id in set(body.anlage_ids) - bereits_zugeordnet:
        await _validate_anlage_fuer_kunde(session, anlage_id, vorgang.kunde_id)
        session.add(
            VorgangAnlage(mandant_id=auth.mandant_id, vorgang_id=vorgang_id, anlage_id=anlage_id)
        )
    await session.flush()

    result = await session.execute(
        select(Anlage)
        .join(VorgangAnlage, VorgangAnlage.anlage_id == Anlage.id)
        .where(VorgangAnlage.vorgang_id == vorgang_id, Anlage.geloescht_am.is_(None))
        .order_by(Anlage.bezeichnung)
    )
    return list(result.scalars().all())


@router.delete(
    "/{vorgang_id}/anlagen/{anlage_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("vorgaenge", "bearbeiten")),
    ],
)
async def remove_vorgang_anlage(
    vorgang_id: UUID,
    anlage_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> None:
    zuordnung = await session.get(VorgangAnlage, {"vorgang_id": vorgang_id, "anlage_id": anlage_id})
    if zuordnung is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zuordnung nicht gefunden")
    await session.delete(zuordnung)
    await session.flush()


@router.get("/{vorgang_id}/emails", response_model=list[EmailLogRead])
async def list_vorgang_emails(
    vorgang_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[EmailLog]:
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None or vorgang.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
    await _require_vorgang_zugriff(session, auth, vorgang)
    result = await session.execute(
        select(EmailLog)
        .where(EmailLog.entity_type == "vorgang", EmailLog.entity_id == vorgang_id)
        .order_by(EmailLog.created_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/{vorgang_id}/emails",
    response_model=EmailLogRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("vorgaenge", "bearbeiten")),
    ],
)
async def send_vorgang_email(
    vorgang_id: UUID,
    body: EmailSenden,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> EmailLog:
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None or vorgang.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
    await _require_vorgang_zugriff(session, auth, vorgang)

    log = await send_email_and_log(
        session,
        auth.mandant_id,
        entity_type="vorgang",
        entity_id=vorgang_id,
        to=body.empfaenger,
        subject=body.betreff,
        body=body.inhalt,
        gesendet_von=auth.user_id,
    )
    return log


@router.patch(
    "/{vorgang_id}",
    response_model=VorgangRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("vorgaenge", "bearbeiten")),
    ],
)
async def update_vorgang(
    vorgang_id: UUID,
    body: VorgangUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Vorgang:
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None or vorgang.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
    await _require_vorgang_zugriff(session, auth, vorgang)

    changes = body.model_dump(exclude_unset=True)
    if changes and vorgang.status in VORGANG_STATUS_GESCHLOSSEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vorgang ist abgeschlossen und kann nicht mehr geändert werden",
        )
    # Kein echtes Vorgang-Feld -- steuert nur die Wiedervorlage-Berechnung
    # weiter unten, sonst wuerde die generische setattr-Schleife es als
    # beliebiges Instanz-Attribut auf dem ORM-Objekt landen lassen.
    wiedervorlage_tage = changes.pop("wiedervorlage_tage", None)
    if wiedervorlage_tage is not None and changes.get("status") != "wartet_kunde":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="wiedervorlage_tage ist nur beim Setzen von status=wartet_kunde gültig",
        )
    alter_status = vorgang.status
    alter_kunde_id = vorgang.kunde_id

    if "kunde_id" in changes:
        neuer_kunde_id = changes["kunde_id"]
        if await session.get(Kunde, neuer_kunde_id) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Kunde nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
        if await ist_auf_zugewiesene_kunden_beschraenkt(
            session, role=auth.role, account_typ_id=auth.account_typ_id
        ) and neuer_kunde_id not in await assigned_kunde_ids(session, auth.user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Dieser Kunde ist dir nicht zugewiesen",
            )
        # Eine bestehende Anlage-Zuordnung gehoerte zum alten Kunden -- wird
        # die neue Anlage nicht im selben Request mitgegeben, bleibt sie
        # sonst inkonsistent (Anlage eines anderen Kunden) an diesem Vorgang
        # haengen. Statt das abzulehnen, wird die Verknuepfung entfernt.
        if "anlage_id" not in changes and vorgang.anlage_id is not None:
            bestehende_anlage = await session.get(Anlage, vorgang.anlage_id)
            if bestehende_anlage is None or bestehende_anlage.kunde_id != neuer_kunde_id:
                changes["anlage_id"] = None
        # Dieselbe Ueberlegung fuer einen bestehenden Standort.
        if "standort_id" not in changes and vorgang.standort_id is not None:
            bestehender_standort = await session.get(Standort, vorgang.standort_id)
            if bestehender_standort is None or bestehender_standort.kunde_id != neuer_kunde_id:
                changes["standort_id"] = None
        # Dieselbe Ueberlegung fuer einen bestehenden Vertrag.
        if "vertrag_id" not in changes and vorgang.vertrag_id is not None:
            bestehender_vertrag = await session.get(Vertrag, vorgang.vertrag_id)
            if bestehender_vertrag is None or bestehender_vertrag.kunde_id != neuer_kunde_id:
                changes["vertrag_id"] = None

    if changes.get("anlage_id") is not None:
        anlage = await session.get(Anlage, changes["anlage_id"])
        if anlage is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Anlage nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
        ziel_kunde_id = changes.get("kunde_id", vorgang.kunde_id)
        if anlage.kunde_id != ziel_kunde_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Anlage gehört nicht zum (neuen) Kunden dieses Vorgangs",
            )

    if changes.get("standort_id") is not None:
        standort = await session.get(Standort, changes["standort_id"])
        if standort is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Standort nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
        ziel_kunde_id = changes.get("kunde_id", vorgang.kunde_id)
        if standort.kunde_id != ziel_kunde_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Standort gehört nicht zum (neuen) Kunden dieses Vorgangs",
            )

    if changes.get("vertrag_id") is not None:
        vertrag = await session.get(Vertrag, changes["vertrag_id"])
        if vertrag is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vertrag nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
        ziel_kunde_id = changes.get("kunde_id", vorgang.kunde_id)
        if vertrag.kunde_id != ziel_kunde_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vertrag gehört nicht zum (neuen) Kunden dieses Vorgangs",
            )

    if changes.get("zugewiesener_user_id") is not None:
        if await session.get(User, changes["zugewiesener_user_id"]) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nutzer nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )

    alter_zugewiesener_user_id = vorgang.zugewiesener_user_id

    for field, value in changes.items():
        setattr(vorgang, field, value)

    if (
        "zugewiesener_user_id" in changes
        and changes["zugewiesener_user_id"] != alter_zugewiesener_user_id
    ):
        neuer_zugewiesener = (
            await session.get(User, changes["zugewiesener_user_id"])
            if changes["zugewiesener_user_id"] is not None
            else None
        )
        session.add(
            VorgangEvent(
                mandant_id=vorgang.mandant_id,
                vorgang_id=vorgang.id,
                event_type="system",
                is_system=True,
                author_user_id=auth.user_id,
                body=(
                    f"Zugewiesen an: {neuer_zugewiesener.name}"
                    if neuer_zugewiesener is not None
                    else "Zuweisung aufgehoben"
                ),
            )
        )

    if "kunde_id" in changes and changes["kunde_id"] != alter_kunde_id:
        alter_kunde = await session.get(Kunde, alter_kunde_id)
        neuer_kunde = await session.get(Kunde, changes["kunde_id"])
        session.add(
            VorgangEvent(
                mandant_id=vorgang.mandant_id,
                vorgang_id=vorgang.id,
                event_type="system",
                is_system=True,
                author_user_id=auth.user_id,
                body=(
                    f"Kunde geändert: {alter_kunde.name if alter_kunde else '?'} → "
                    f"{neuer_kunde.name if neuer_kunde else '?'}"
                ),
            )
        )

    if "status" in changes and changes["status"] != alter_status:
        if changes["status"] == "abgeschlossen":
            offene_formulare = await offene_pflichtformulare(session, vorgang)
            if offene_formulare:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Vorgang kann nicht abgeschlossen werden, folgende Pflicht-Formulare "
                        f"fehlen noch: {', '.join(offene_formulare)}"
                    ),
                )
            await close_vorgang(
                session,
                vorgang,
                alter_status=alter_status,
                author_user_id=auth.user_id,
            )
            vorgang.wiedervorlage_am = None
        else:
            session.add(
                VorgangEvent(
                    mandant_id=vorgang.mandant_id,
                    vorgang_id=vorgang.id,
                    event_type="status_change",
                    author_user_id=auth.user_id,
                    payload={"von": alter_status, "nach": changes["status"]},
                )
            )
            if changes["status"] == "wartet_kunde":
                mandant = await session.get(Mandant, auth.mandant_id)
                tage = (
                    wiedervorlage_tage
                    or mandant.wiedervorlage_standard_tage
                    or get_settings().wiedervorlage_default_tage
                )
                vorgang.wiedervorlage_am = datetime.now(timezone.utc) + timedelta(days=tage)
            else:
                # Vorgang verlaesst wartet_kunde in einen anderen offenen
                # Status (z.B. storniert oder zurueck in Bearbeitung) --
                # eine noch ausstehende Wiedervorlage bezog sich auf den
                # Warte-Zustand und ist damit hinfaellig.
                vorgang.wiedervorlage_am = None

    await session.flush()
    if changes:
        await session.refresh(vorgang)
        await event_bus.publish(
            auth.mandant_id, "feed_update", {"vorgang_id": str(vorgang.id), "reason": "geaendert"}
        )
    return await _mit_zugewiesenem_namen(session, vorgang)


@router.post(
    "/{vorgang_id}/folge-auftrag",
    response_model=VorgangRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("vorgaenge", "erstellen")),
    ],
)
async def folge_auftrag_erstellen(
    vorgang_id: UUID,
    body: VorgangFolgeAuftragErstellen,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Vorgang:
    """Legt aus diesem Vorgang einen Folge-Auftrag an -- unabhaengig vom
    aktuellen Status der Quelle (siehe create_folge_vorgang) und mit
    beliebigem Leistungstyp. Ersetzt den frueheren Automatismus, der nur
    beim Abschluss eines Beratungs-Vorgangs griff."""
    quelle = await session.get(Vorgang, vorgang_id)
    if quelle is None or quelle.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
    await _require_vorgang_zugriff(session, auth, quelle)

    folge_vorgang = await create_folge_vorgang(
        session, quelle, leistungstyp=body.leistungstyp, author_user_id=auth.user_id
    )
    await session.flush()
    await event_bus.publish(
        auth.mandant_id, "feed_update", {"vorgang_id": str(folge_vorgang.id), "reason": "erstellt"}
    )
    return folge_vorgang


@router.post(
    "/{vorgang_id}/uebernehmen",
    response_model=VorgangRead,
    dependencies=[Depends(require_recht("vorgaenge", "sehen"))],
)
async def uebernehmen(
    vorgang_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Vorgang:
    """Ticket übernehmen: jeder Mitarbeiter mit "vorgaenge"."sehen" (also
    praktisch jeder) darf einen Vorgang selbst uebernehmen, sofern sein
    Account-Typ das erlaubt (siehe app/services/rechte_service.py:
    darf_vorgang_selbst_uebernehmen) -- bewusst eine eigene, engere
    Berechtigung statt "vorgaenge"."bearbeiten", damit auch Mitarbeiter ohne
    generelle Bearbeiten-Rechte sich selbst zuweisen koennen. Ein bereits
    zugewiesener Vorgang darf ueberschrieben werden (z.B. Vertretung/Urlaub)."""
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None or vorgang.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
    await _require_vorgang_zugriff(session, auth, vorgang)

    if vorgang.status in VORGANG_STATUS_GESCHLOSSEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vorgang ist abgeschlossen und kann nicht mehr geändert werden",
        )
    if not await darf_vorgang_selbst_uebernehmen(
        session, role=auth.role, account_typ_id=auth.account_typ_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Du darfst Vorgänge nicht selbst übernehmen",
        )

    alter_status = vorgang.status
    vorgang.zugewiesener_user_id = auth.user_id
    if alter_status == "neu":
        vorgang.status = "in_arbeit"

    author = await session.get(User, auth.user_id)
    session.add(
        VorgangEvent(
            mandant_id=vorgang.mandant_id,
            vorgang_id=vorgang.id,
            event_type="system",
            is_system=True,
            author_user_id=auth.user_id,
            body=f"Übernommen von {author.name if author else '?'}",
        )
    )
    if alter_status == "neu":
        session.add(
            VorgangEvent(
                mandant_id=vorgang.mandant_id,
                vorgang_id=vorgang.id,
                event_type="status_change",
                author_user_id=auth.user_id,
                payload={"von": alter_status, "nach": "in_arbeit"},
            )
        )

    await session.flush()
    await session.refresh(vorgang)
    await event_bus.publish(
        auth.mandant_id, "feed_update", {"vorgang_id": str(vorgang.id), "reason": "geaendert"}
    )
    return await _mit_zugewiesenem_namen(session, vorgang)


@router.patch(
    "/{vorgang_id}/partner-zuweisung",
    response_model=VorgangPartnerZuweisungResponse,
    dependencies=[
        Depends(require_roles("mandant_admin", "disponent")),
        Depends(require_module("nachunternehmer")),
    ],
)
async def vorgang_partner_zuweisen(
    vorgang_id: UUID,
    body: VorgangPartnerZuweisung,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorgangPartnerZuweisungResponse:
    """Delegiert diesen Vorgang komplett an einen Nachunternehmer (fuer eine
    Teilleistung stattdessen einen Kind-Vorgang mit parent_vorgang_id
    anlegen und diesen hier zuweisen). Der Partner muss die Delegation
    aktiv annehmen/ablehnen (siehe app/api/routes/partner_portal.py) --
    partner_id=None hebt eine bestehende Zuweisung wieder auf."""
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")

    warnung = False
    if body.partner_id is None:
        vorgang.partner_id = None
        vorgang.partner_freigabe_status = None
        vorgang.partner_ablehnung_grund = None
        vorgang.partner_honorar_netto = None
    else:
        partner = await session.get(Partner, body.partner_id)
        if partner is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Partner nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
        vorgang.partner_id = body.partner_id
        vorgang.partner_freigabe_status = "vorgeschlagen"
        vorgang.partner_ablehnung_grund = None
        vorgang.partner_honorar_netto = body.partner_honorar_netto
        warnung = not await partner_hat_gueltige_freistellungsbescheinigung(session, partner.id)

        session.add(
            VorgangEvent(
                mandant_id=vorgang.mandant_id,
                vorgang_id=vorgang.id,
                event_type="system",
                is_system=True,
                author_user_id=auth.user_id,
                body=f"Als Teilleistung/Auftrag an Nachunternehmer '{partner.name}' vorgeschlagen",
                payload={"partner_id": str(partner.id)},
            )
        )

    await session.flush()
    await event_bus.publish(
        auth.mandant_id, "feed_update", {"vorgang_id": str(vorgang.id), "reason": "geaendert"}
    )
    return VorgangPartnerZuweisungResponse(
        vorgang_id=vorgang.id,
        partner_id=vorgang.partner_id,
        partner_freigabe_status=vorgang.partner_freigabe_status,
        freistellungsbescheinigung_warnung=warnung,
    )


@router.delete(
    "/{vorgang_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("vorgaenge", "loeschen")),
    ],
)
async def delete_vorgang(
    vorgang_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    # Papierkorb statt Hard-Delete: kaskadiert auf Maengel, Angebote,
    # Rechnungen, Materialbedarfe, Termine und untergeordnete Vorgaenge
    # dieses Vorgangs (siehe app/services/papierkorb_service.py). Bisher gab
    # es fuer einen Vorgang gar keinen Loesch-Endpoint (nur den Status
    # "storniert") -- dieser ist neu und primaer fuer loesch_operativ gedacht.
    vorgang = await papierkorb_service.soft_delete(
        session, entity_typ="vorgang", entity_id=vorgang_id, actor_user_id=auth.user_id
    )
    if vorgang is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
    await log_action(
        session,
        aktion="vorgang_geloescht",
        mandant_id=auth.mandant_id,
        actor_user_id=auth.user_id,
        entity_type="vorgang",
        entity_id=vorgang_id,
        payload={"vorgangsnummer": vorgang.vorgangsnummer},
    )
