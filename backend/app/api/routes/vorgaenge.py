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
from app.models.anlage import Anlage
from app.models.kunde import Kunde
from app.models.standort import Standort
from app.models.vertrag import Vertrag
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.vorgang import VorgangCreate, VorgangRead, VorgangUpdate
from app.services.csv_service import csv_response
from app.services.event_bus import event_bus
from app.services.numbering_service import next_vorgangsnummer
from app.services.vorgang_completion_service import (
    VORGANG_STATUS_GESCHLOSSEN,
    close_vorgang,
)
from app.services.zuweisung_service import assigned_kunde_ids

router = APIRouter(
    prefix="/api/vorgaenge",
    tags=["vorgaenge"],
    dependencies=[
        Depends(require_roles("mandant_admin", "disponent", "techniker", "controller", "mitarbeiter"))
    ],
)


@router.get("", response_model=list[VorgangRead], dependencies=[Depends(require_recht("vorgaenge", "sehen"))])
async def list_vorgaenge(
    status_filter: str | None = Query(default=None, alias="status"),
    kunde_id: UUID | None = Query(default=None),
    anlage_id: UUID | None = Query(default=None),
    leistungstyp: str | None = Query(default=None),
    abrechnungsart: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Vorgang]:
    stmt = select(Vorgang).order_by(Vorgang.last_activity_at.desc(), Vorgang.id.desc()).limit(limit)
    if status_filter:
        stmt = stmt.where(Vorgang.status == status_filter)
    if kunde_id:
        stmt = stmt.where(Vorgang.kunde_id == kunde_id)
    if anlage_id:
        stmt = stmt.where(Vorgang.anlage_id == anlage_id)
    if leistungstyp:
        stmt = stmt.where(Vorgang.leistungstyp == leistungstyp)
    if abrechnungsart:
        stmt = stmt.where(Vorgang.abrechnungsart == abrechnungsart)
    if auth.role == "techniker":
        stmt = stmt.where(Vorgang.kunde_id.in_(await assigned_kunde_ids(session, auth.user_id)))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _validate_references(
    session: AsyncSession, auth: AuthContext, body: VorgangCreate
) -> None:
    kunde = await session.get(Kunde, body.kunde_id)
    if kunde is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kunde nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if auth.role == "techniker" and body.kunde_id not in await assigned_kunde_ids(
        session, auth.user_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dieser Kunde ist dir nicht zugewiesen",
        )
    if body.anlage_id is not None:
        anlage = await session.get(Anlage, body.anlage_id)
        if anlage is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Anlage nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
        if anlage.kunde_id != body.kunde_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Anlage gehört nicht zum angegebenen Kunden",
            )
        if not anlage.aktiv:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Anlage ist inaktiv und steht für neue Vorgänge nicht zur Auswahl",
            )
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
    dependencies=[Depends(require_recht("vorgaenge", "bearbeiten"))],
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
        client_uuid=body.client_uuid,
    )
    session.add(vorgang)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Vorgangsnummer bereits vergeben"
        ) from exc

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
    if auth.role == "techniker" and vorgang.kunde_id not in await assigned_kunde_ids(
        session, auth.user_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")


@router.get("/export/csv", dependencies=[Depends(require_module("statistik"))])
async def export_vorgaenge_csv(
    status_filter: str | None = Query(default=None, alias="status"),
    kunde_id: UUID | None = Query(default=None),
    von: date | None = Query(default=None),
    bis: date | None = Query(default=None),
    auth: AuthContext = Depends(require_roles("mandant_admin", "disponent")),
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
    if vorgang is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
    await _require_vorgang_zugriff(session, auth, vorgang)
    return vorgang


@router.patch(
    "/{vorgang_id}",
    response_model=VorgangRead,
    dependencies=[Depends(require_recht("vorgaenge", "bearbeiten"))],
)
async def update_vorgang(
    vorgang_id: UUID,
    body: VorgangUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Vorgang:
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorgang nicht gefunden")
    await _require_vorgang_zugriff(session, auth, vorgang)

    changes = body.model_dump(exclude_unset=True)
    if changes and vorgang.status in VORGANG_STATUS_GESCHLOSSEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vorgang ist abgeschlossen und kann nicht mehr geändert werden",
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
        if auth.role == "techniker" and neuer_kunde_id not in await assigned_kunde_ids(
            session, auth.user_id
        ):
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

    for field, value in changes.items():
        setattr(vorgang, field, value)

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
            await close_vorgang(
                session, vorgang, alter_status=alter_status, author_user_id=auth.user_id
            )
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

    await session.flush()
    if changes:
        await session.refresh(vorgang)
        await event_bus.publish(
            auth.mandant_id, "feed_update", {"vorgang_id": str(vorgang.id), "reason": "geaendert"}
        )
    return vorgang
