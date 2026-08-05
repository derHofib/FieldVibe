from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
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
from app.models.mandant import Mandant
from app.models.user import User
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.models.zeiterfassung import Zeiterfassung
from app.schemas.zeiterfassung import ZeiterfassungRead, ZeiterfassungStart, ZeiterfassungStatistik
from app.services.csv_service import csv_response
from app.services.event_bus import event_bus
from app.services.pdf_service import generate_wochenzettel_pdf
from app.services.rechte_service import (
    darf_fremde_mitarbeiterdaten_einsehen,
    ist_auf_zugewiesene_kunden_beschraenkt,
)
from app.services.vorgang_completion_service import VORGANG_STATUS_GESCHLOSSEN
from app.services.zuweisung_service import assigned_kunde_ids

router = APIRouter(
    prefix="/api/zeiterfassung",
    tags=["zeiterfassung"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("vorgaenge", "sehen")),
    ],
)


def _montag_dieser_woche(jetzt: datetime) -> datetime:
    tage_seit_montag = jetzt.weekday()
    montag_datum = jetzt.date() - timedelta(days=tage_seit_montag)
    return datetime.combine(montag_datum, time.min, tzinfo=timezone.utc)


def _tagesbeginn(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


@router.get("", response_model=list[ZeiterfassungRead])
async def list_zeiterfassung(
    vorgang_id: UUID | None = Query(default=None),
    techniker_id: UUID | None = Query(default=None),
    von: date | None = Query(default=None),
    bis: date | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Zeiterfassung]:
    stmt = select(Zeiterfassung).order_by(Zeiterfassung.start_at.desc())
    if vorgang_id:
        stmt = stmt.where(Zeiterfassung.vorgang_id == vorgang_id)
    if von:
        stmt = stmt.where(Zeiterfassung.start_at >= _tagesbeginn(von))
    if bis:
        stmt = stmt.where(Zeiterfassung.start_at < _tagesbeginn(bis + timedelta(days=1)))

    if techniker_id:
        # Ausdruecklich nach einem Techniker gefiltert (z.B. die eigene
        # Statistik-Seite): dessen komplette eigene Historie zaehlt, auch
        # fuer Kunden, denen er inzwischen nicht mehr zugewiesen ist --
        # die kunde_id-Einschraenkung unten ist nur fuer den impliziten
        # Fall (kein techniker_id, z.B. Zeiterfassungen zu EINEM Vorgang)
        # gedacht.
        if techniker_id != auth.user_id and not await darf_fremde_mitarbeiterdaten_einsehen(
            session, role=auth.role, account_typ_id=auth.account_typ_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Nur eigene Zeiterfassungen einsehbar"
            )
        stmt = stmt.where(Zeiterfassung.techniker_id == techniker_id)
    elif await ist_auf_zugewiesene_kunden_beschraenkt(
        session, role=auth.role, account_typ_id=auth.account_typ_id
    ):
        stmt = stmt.where(
            Zeiterfassung.vorgang_id.in_(
                select(Vorgang.id).where(
                    Vorgang.kunde_id.in_(await assigned_kunde_ids(session, auth.user_id))
                )
            )
        )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get(
    "/export/csv",
    dependencies=[
        Depends(require_module("statistik")),
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("mitarbeiterverwaltung", "bearbeiten")),
    ],
)
async def export_zeiterfassung_csv(
    techniker_id: UUID | None = Query(default=None),
    von: date | None = Query(default=None),
    bis: date | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    stmt = select(Zeiterfassung).order_by(Zeiterfassung.start_at.asc())
    if techniker_id:
        stmt = stmt.where(Zeiterfassung.techniker_id == techniker_id)
    if von:
        stmt = stmt.where(Zeiterfassung.start_at >= _tagesbeginn(von))
    if bis:
        stmt = stmt.where(Zeiterfassung.start_at < _tagesbeginn(bis + timedelta(days=1)))
    eintraege = list((await session.execute(stmt)).scalars().all())

    technikers_by_id: dict[UUID, User | None] = {}
    vorgaenge_by_id: dict[UUID, Vorgang | None] = {}
    rows = []
    for e in eintraege:
        if e.techniker_id not in technikers_by_id:
            technikers_by_id[e.techniker_id] = await session.get(User, e.techniker_id)
        techniker = technikers_by_id[e.techniker_id]
        if e.vorgang_id not in vorgaenge_by_id:
            vorgaenge_by_id[e.vorgang_id] = await session.get(Vorgang, e.vorgang_id)
        vorgang = vorgaenge_by_id[e.vorgang_id]
        dauer_stunden = (
            (e.ende_at - e.start_at).total_seconds() / 3600 if e.ende_at else None
        )
        rows.append(
            [
                e.start_at.strftime("%d.%m.%Y"),
                techniker.name if techniker else "",
                vorgang.vorgangsnummer if vorgang else "",
                e.taetigkeit or "",
                e.start_at.strftime("%H:%M"),
                e.ende_at.strftime("%H:%M") if e.ende_at else "",
                f"{dauer_stunden:.2f}".replace(".", ",") if dauer_stunden is not None else "",
                "Ja" if e.abrechenbar else "Nein",
            ]
        )

    return csv_response(
        ["Datum", "Techniker", "Vorgang", "Tätigkeit", "Von", "Bis", "Dauer (Std.)", "Abrechenbar"],
        rows,
        "Zeiterfassung.csv",
    )


@router.get(
    "/statistik",
    response_model=ZeiterfassungStatistik,
    dependencies=[Depends(require_module("statistik"))],
)
async def get_statistik(
    techniker_id: UUID | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ZeiterfassungStatistik:
    ziel_id = techniker_id or auth.user_id
    if ziel_id != auth.user_id and not await darf_fremde_mitarbeiterdaten_einsehen(
        session, role=auth.role, account_typ_id=auth.account_typ_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Nur eigene Statistik einsehbar"
        )

    jetzt = datetime.now(timezone.utc)
    wochenstart = _montag_dieser_woche(jetzt)
    monatsstart = datetime(jetzt.year, jetzt.month, 1, tzinfo=timezone.utc)
    jahresstart = datetime(jetzt.year, 1, 1, tzinfo=timezone.utc)

    async def _stunden_seit(start: datetime) -> Decimal:
        result = await session.execute(
            select(Zeiterfassung).where(
                Zeiterfassung.techniker_id == ziel_id,
                Zeiterfassung.start_at >= start,
                Zeiterfassung.ende_at.isnot(None),
            )
        )
        sekunden = sum(
            (e.ende_at - e.start_at).total_seconds() for e in result.scalars().all()
        )
        return (Decimal(sekunden) / Decimal(3600)).quantize(Decimal("0.1"))

    return ZeiterfassungStatistik(
        wochenstunden=await _stunden_seit(wochenstart),
        monatsstunden=await _stunden_seit(monatsstart),
        jahresstunden=await _stunden_seit(jahresstart),
    )


@router.get("/wochenzettel-pdf", dependencies=[Depends(require_module("statistik"))])
async def wochenzettel_pdf(
    woche_start: date = Query(...),
    techniker_id: UUID | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    ziel_id = techniker_id or auth.user_id
    if ziel_id != auth.user_id and not await darf_fremde_mitarbeiterdaten_einsehen(
        session, role=auth.role, account_typ_id=auth.account_typ_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Nur eigener Wochenzettel abrufbar"
        )

    techniker = await session.get(User, ziel_id)
    if techniker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Techniker nicht gefunden")
    mandant = await session.get(Mandant, auth.mandant_id)

    woche_ende = woche_start + timedelta(days=6)
    result = await session.execute(
        select(Zeiterfassung)
        .where(
            Zeiterfassung.techniker_id == ziel_id,
            Zeiterfassung.start_at >= _tagesbeginn(woche_start),
            Zeiterfassung.start_at < _tagesbeginn(woche_start + timedelta(days=7)),
        )
        .order_by(Zeiterfassung.start_at)
    )
    eintraege = list(result.scalars().all())
    vorgaenge_by_id: dict[UUID, Vorgang | None] = {}
    for eintrag in eintraege:
        if eintrag.vorgang_id not in vorgaenge_by_id:
            vorgaenge_by_id[eintrag.vorgang_id] = await session.get(Vorgang, eintrag.vorgang_id)
    paare = [(eintrag, vorgaenge_by_id.get(eintrag.vorgang_id)) for eintrag in eintraege]

    pdf_bytes = generate_wochenzettel_pdf(mandant, techniker, woche_start, woche_ende, paare)
    sicherer_name = "".join(c if c.isalnum() else "_" for c in techniker.name)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'inline; filename="Wochenzettel-{sicherer_name}-{woche_start.isoformat()}.pdf"'
            )
        },
    )


@router.get("/laufend", response_model=ZeiterfassungRead | None)
async def get_laufender_timer(
    auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> Zeiterfassung | None:
    result = await session.execute(
        select(Zeiterfassung).where(
            Zeiterfassung.techniker_id == auth.user_id, Zeiterfassung.ende_at.is_(None)
        )
    )
    return result.scalar_one_or_none()


@router.post(
    "/start",
    response_model=ZeiterfassungRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_recht("vorgaenge", "bearbeiten"))],
)
async def start_timer(
    body: ZeiterfassungStart,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Zeiterfassung:
    vorgang = await session.get(Vorgang, body.vorgang_id)
    if vorgang is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if await ist_auf_zugewiesene_kunden_beschraenkt(
        session, role=auth.role, account_typ_id=auth.account_typ_id
    ) and vorgang.kunde_id not in await assigned_kunde_ids(session, auth.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Dieser Kunde ist dir nicht zugewiesen"
        )
    if vorgang.status in VORGANG_STATUS_GESCHLOSSEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vorgang ist abgeschlossen und kann nicht mehr bebucht werden",
        )

    eintrag = Zeiterfassung(
        mandant_id=auth.mandant_id,
        vorgang_id=body.vorgang_id,
        techniker_id=auth.user_id,
        start_at=datetime.now(timezone.utc),
        taetigkeit=body.taetigkeit,
        abrechenbar=body.abrechenbar,
    )
    session.add(eintrag)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Es läuft bereits ein Timer für diesen Techniker",
        ) from exc

    session.add(
        VorgangEvent(
            mandant_id=auth.mandant_id,
            vorgang_id=body.vorgang_id,
            event_type="zeit_start",
            author_user_id=auth.user_id,
            payload={"zeiterfassung_id": str(eintrag.id), "taetigkeit": body.taetigkeit},
        )
    )
    await session.flush()

    await event_bus.publish(
        auth.mandant_id,
        "timer",
        {"vorgang_id": str(body.vorgang_id), "techniker_id": str(auth.user_id), "laeuft": True},
    )
    return eintrag


@router.post("/{zeiterfassung_id}/stop", response_model=ZeiterfassungRead)
async def stop_timer(
    zeiterfassung_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Zeiterfassung:
    eintrag = await session.get(Zeiterfassung, zeiterfassung_id)
    if eintrag is None or eintrag.techniker_id != auth.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Zeiterfassung nicht gefunden"
        )
    if eintrag.ende_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Timer läuft nicht mehr"
        )

    eintrag.ende_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(eintrag)

    session.add(
        VorgangEvent(
            mandant_id=auth.mandant_id,
            vorgang_id=eintrag.vorgang_id,
            event_type="zeit_stop",
            author_user_id=auth.user_id,
            payload={
                "zeiterfassung_id": str(eintrag.id),
                "dauer_sekunden": int((eintrag.ende_at - eintrag.start_at).total_seconds()),
            },
        )
    )
    await session.flush()

    await event_bus.publish(
        auth.mandant_id,
        "timer",
        {"vorgang_id": str(eintrag.vorgang_id), "techniker_id": str(auth.user_id), "laeuft": False},
    )
    return eintrag
