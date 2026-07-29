from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.models.anlage import Anlage
from app.models.dauerauftrag import Dauerauftrag
from app.models.kunde import Kunde
from app.models.mangel import Mangel
from app.models.pruefzyklus import Pruefzyklus
from app.models.vertrag import Vertrag
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.vorgang import VorgangCreate, VorgangRead, VorgangUpdate
from app.services.date_utils import add_months
from app.services.event_bus import event_bus
from app.services.numbering_service import next_vorgangsnummer
from app.services.zuweisung_service import assigned_kunde_ids

router = APIRouter(
    prefix="/api/vorgaenge",
    tags=["vorgaenge"],
    dependencies=[Depends(require_roles("mandant_admin", "disponent", "techniker"))],
)


@router.get("", response_model=list[VorgangRead])
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
    if body.vertrag_id is not None and await session.get(Vertrag, body.vertrag_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vertrag nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if body.parent_vorgang_id is not None and await session.get(Vorgang, body.parent_vorgang_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Übergeordneter Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )


@router.post("", response_model=VorgangRead, status_code=status.HTTP_201_CREATED)
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


@router.get("/{vorgang_id}", response_model=VorgangRead)
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


@router.patch("/{vorgang_id}", response_model=VorgangRead)
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
    alter_status = vorgang.status

    for field, value in changes.items():
        setattr(vorgang, field, value)

    if "status" in changes and changes["status"] != alter_status:
        if changes["status"] == "abgeschlossen" and vorgang.abgeschlossen_am is None:
            vorgang.abgeschlossen_am = datetime.now(timezone.utc)
        session.add(
            VorgangEvent(
                mandant_id=vorgang.mandant_id,
                vorgang_id=vorgang.id,
                event_type="status_change",
                author_user_id=auth.user_id,
                payload={"von": alter_status, "nach": changes["status"]},
            )
        )
        if changes["status"] == "abgeschlossen":
            # Schliesst dieser Vorgang einen vom Pruefzyklen-Scheduler
            # angelegten Auftrag ab, gilt die Pruefung als durchgefuehrt:
            # Faelligkeit fortschreiben, offener_vorgang_id leeren -- sonst
            # wuerde der naechste Scheduler-Lauf sofort einen neuen Vorgang
            # fuer denselben (jetzt erledigten) Zyklus anlegen.
            zyklus = (
                await session.execute(
                    select(Pruefzyklus).where(Pruefzyklus.offener_vorgang_id == vorgang.id)
                )
            ).scalar_one_or_none()
            if zyklus is not None:
                zyklus.letzte_pruefung_am = vorgang.abgeschlossen_am.date()
                zyklus.naechste_pruefung_am = add_months(
                    zyklus.letzte_pruefung_am, zyklus.intervall_monate
                )
                zyklus.offener_vorgang_id = None

            # Schliesst dieser Vorgang einen Dauerauftrag ab (wiederkehrender
            # Auftrag, siehe app/models/dauerauftrag.py): naechste
            # Faelligkeit fortschreiben und offener_vorgang_id leeren, damit
            # der naechste Scheduler-Lauf ueberhaupt erst einen Folge-Vorgang
            # anlegen darf -- solange dieser hier offen war, geschah das nie.
            dauerauftrag = (
                await session.execute(
                    select(Dauerauftrag).where(Dauerauftrag.offener_vorgang_id == vorgang.id)
                )
            ).scalar_one_or_none()
            if dauerauftrag is not None:
                geplante_faelligkeit = dauerauftrag.naechste_faelligkeit_am
                abgeschlossen_datum = vorgang.abgeschlossen_am.date()
                tage_abweichung = (abgeschlossen_datum - geplante_faelligkeit).days

                if (
                    dauerauftrag.toleranz_frueh_tage is not None
                    and tage_abweichung < -dauerauftrag.toleranz_frueh_tage
                ):
                    session.add(
                        VorgangEvent(
                            mandant_id=vorgang.mandant_id,
                            vorgang_id=vorgang.id,
                            event_type="system",
                            is_system=True,
                            body=(
                                f"Hinweis: {-tage_abweichung} Tage vor der geplanten "
                                f"Fälligkeit ({geplante_faelligkeit.isoformat()}) abgeschlossen."
                            ),
                        )
                    )
                elif (
                    dauerauftrag.toleranz_spaet_tage is not None
                    and tage_abweichung > dauerauftrag.toleranz_spaet_tage
                ):
                    session.add(
                        VorgangEvent(
                            mandant_id=vorgang.mandant_id,
                            vorgang_id=vorgang.id,
                            event_type="system",
                            is_system=True,
                            body=(
                                f"Hinweis: {tage_abweichung} Tage nach der geplanten "
                                f"Fälligkeit ({geplante_faelligkeit.isoformat()}) abgeschlossen."
                            ),
                        )
                    )

                # "rollierend" (Default): Frist wandert mit dem tatsaechlichen
                # Abschlussdatum, damit liegen gebliebene Auftraege sich nicht
                # selbst einholen. "fest": Frist bleibt an einem festen
                # Kalenderrhythmus verankert, unabhaengig davon, wann
                # tatsaechlich abgeschlossen wurde.
                basis = (
                    abgeschlossen_datum if dauerauftrag.modus == "rollierend" else geplante_faelligkeit
                )
                dauerauftrag.naechste_faelligkeit_am = basis + timedelta(days=dauerauftrag.intervall_tage)
                dauerauftrag.offener_vorgang_id = None

            # Schliesst dieser Vorgang eine aus einem angenommenen Angebot
            # entstandene Reparatur ab, gelten die zugehoerigen Maengel als
            # behoben (siehe app/api/routes/angebote.py: dort wird
            # reparatur_vorgang_id beim Annehmen des Angebots gesetzt).
            offene_maengel = (
                await session.execute(
                    select(Mangel).where(
                        Mangel.reparatur_vorgang_id == vorgang.id, Mangel.status != "behoben"
                    )
                )
            ).scalars().all()
            for mangel in offene_maengel:
                mangel.status = "behoben"
                mangel.behoben_am = vorgang.abgeschlossen_am

    await session.flush()
    if changes:
        await session.refresh(vorgang)
        await event_bus.publish(
            auth.mandant_id, "feed_update", {"vorgang_id": str(vorgang.id), "reason": "geaendert"}
        )
    return vorgang
