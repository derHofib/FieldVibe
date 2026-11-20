from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_recht, require_roles
from app.models.anlage import Anlage
from app.models.kunde import Kunde
from app.models.kundenportal import KundenportalZugang
from app.models.user import User
from app.models.standort import Standort
from app.models.vorgang import Vorgang
from app.models.vorgang_anfrage import VorgangAnfrage
from app.models.vorgang_event import VorgangEvent
from app.schemas.vorgang_anfrage import (
    VorgangAnfrageAblehnen,
    VorgangAnfrageAnnehmen,
    VorgangAnfrageRead,
)
from app.services.event_bus import event_bus
from app.services.numbering_service import next_vorgangsnummer
from app.services.zuweisung_service import erlaubte_kunde_ids, require_kunde_zugriff

router = APIRouter(
    prefix="/api/vorgang-anfragen",
    tags=["vorgang-anfragen"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("vorgaenge", "bearbeiten")),
    ],
)


def _select_mit_namen():
    return (
        select(
            VorgangAnfrage,
            Kunde.name,
            Standort.bezeichnung,
            Anlage.bezeichnung,
            KundenportalZugang.name,
            KundenportalZugang.email,
            Vorgang.vorgangsnummer,
            User.name,
        )
        .outerjoin(Kunde, Kunde.id == VorgangAnfrage.kunde_id)
        .outerjoin(Standort, Standort.id == VorgangAnfrage.standort_id)
        .outerjoin(Anlage, Anlage.id == VorgangAnfrage.anlage_id)
        .outerjoin(KundenportalZugang, KundenportalZugang.id == VorgangAnfrage.kundenportal_zugang_id)
        .outerjoin(Vorgang, Vorgang.id == VorgangAnfrage.vorgang_id)
        .outerjoin(User, User.id == VorgangAnfrage.bearbeitet_von)
    )


def _zeile_zu_read(row) -> VorgangAnfrageRead:
    (anfrage, kunde_name, standort_bez, anlage_bez, zugang_name, zugang_email, vorgang_nr, bearbeiter) = row
    return VorgangAnfrageRead.model_validate(anfrage).model_copy(
        update={
            "kunde_name": kunde_name,
            "standort_bezeichnung": standort_bez,
            "anlage_bezeichnung": anlage_bez,
            "gestellt_von_name": zugang_name,
            "gestellt_von_email": zugang_email,
            "vorgang_nummer": vorgang_nr,
            "bearbeitet_von_name": bearbeiter,
        }
    )


async def _lade_read(session: AsyncSession, anfrage_id: UUID) -> VorgangAnfrageRead:
    # Nach flush/refresh neu lesen, damit auch frisch gesetzte Vorgang-/Bearbeiter-Namen enthalten sind.
    row = (
        await session.execute(_select_mit_namen().where(VorgangAnfrage.id == anfrage_id))
    ).one()
    return _zeile_zu_read(row)


@router.get("", response_model=list[VorgangAnfrageRead])
async def list_anfragen(
    status_filter: str | None = Query(default=None, alias="status"),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[VorgangAnfrageRead]:
    stmt = (
        _select_mit_namen()
        .where(VorgangAnfrage.geloescht_am.is_(None))
        .order_by(VorgangAnfrage.created_at.desc())
    )
    if status_filter:
        stmt = stmt.where(VorgangAnfrage.status == status_filter)
    erlaubte_kunden = await erlaubte_kunde_ids(session, auth)
    if erlaubte_kunden is not None:
        stmt = stmt.where(VorgangAnfrage.kunde_id.in_(erlaubte_kunden))
    result = await session.execute(stmt)
    return [_zeile_zu_read(row) for row in result.all()]


@router.get("/{anfrage_id}", response_model=VorgangAnfrageRead)
async def get_anfrage(
    anfrage_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorgangAnfrageRead:
    await _require_anfrage(session, auth, anfrage_id)
    return await _lade_read(session, anfrage_id)


async def _require_anfrage(session: AsyncSession, auth: AuthContext, anfrage_id: UUID) -> VorgangAnfrage:
    anfrage = await session.get(VorgangAnfrage, anfrage_id)
    if anfrage is None or anfrage.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anfrage nicht gefunden")
    await require_kunde_zugriff(session, auth, anfrage.kunde_id, "Anfrage nicht gefunden")
    return anfrage


def _require_offen(anfrage: VorgangAnfrage) -> None:
    if anfrage.status != "offen":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Anfrage wurde bereits bearbeitet",
        )


@router.post("/{anfrage_id}/annehmen", response_model=VorgangAnfrageRead)
async def annehmen(
    anfrage_id: UUID,
    body: VorgangAnfrageAnnehmen,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorgangAnfrageRead:
    anfrage = await _require_anfrage(session, auth, anfrage_id)
    _require_offen(anfrage)

    # Zwischen Anfrage und Annahme koennen Anlage/Standort inzwischen
    # deaktiviert worden sein -- dieselbe Regel wie bei einer direkt vom
    # Mitarbeiter angelegten Vorgangs-Neuanlage gilt daher auch hier.
    if anfrage.anlage_id is not None:
        anlage = await session.get(Anlage, anfrage.anlage_id)
        if anlage is None or not anlage.aktiv:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Verknüpfte Anlage ist inzwischen inaktiv oder gelöscht",
            )
    if anfrage.standort_id is not None:
        standort = await session.get(Standort, anfrage.standort_id)
        if standort is None or not standort.aktiv:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Verknüpfter Standort ist inzwischen inaktiv oder gelöscht",
            )

    vorgangsnummer = await next_vorgangsnummer(session, auth.mandant_id)
    vorgang = Vorgang(
        mandant_id=auth.mandant_id,
        vorgangsnummer=vorgangsnummer,
        kunde_id=anfrage.kunde_id,
        anlage_id=anfrage.anlage_id,
        standort_id=anfrage.standort_id,
        titel=anfrage.titel,
        beschreibung=anfrage.beschreibung,
        abrechnungsart=body.abrechnungsart,
        leistungstyp=anfrage.leistungstyp,
        prioritaet=body.prioritaet,
        erstellt_von_kundenportal_zugang_id=anfrage.kundenportal_zugang_id,
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
            kundensichtbar=True,
            body="Vorgang aus Kundenanfrage angenommen",
            payload={"status": vorgang.status, "vorgang_anfrage_id": str(anfrage.id)},
        )
    )

    anfrage.status = "angenommen"
    anfrage.vorgang_id = vorgang.id
    anfrage.bearbeitet_von = auth.user_id
    anfrage.bearbeitet_am = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(anfrage)

    await event_bus.publish(
        auth.mandant_id, "feed_update", {"vorgang_id": str(vorgang.id), "reason": "erstellt"}
    )
    return await _lade_read(session, anfrage.id)


@router.post("/{anfrage_id}/ablehnen", response_model=VorgangAnfrageRead)
async def ablehnen(
    anfrage_id: UUID,
    body: VorgangAnfrageAblehnen,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> VorgangAnfrageRead:
    anfrage = await _require_anfrage(session, auth, anfrage_id)
    _require_offen(anfrage)

    anfrage.status = "abgelehnt"
    anfrage.ablehnungsgrund = body.ablehnungsgrund
    anfrage.bearbeitet_von = auth.user_id
    anfrage.bearbeitet_am = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(anfrage)
    return await _lade_read(session, anfrage.id)
