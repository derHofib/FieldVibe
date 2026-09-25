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
from app.models.anlage import Anlage
from app.models.leistungsverzeichnis import LeistungsverzeichnisKunde, LeistungsverzeichnisPosition
from app.models.mandant import Mandant
from app.models.user import User
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.models.zeiterfassung import Zeiterfassung
from app.models.zeiterfassung_aenderung import ZeiterfassungAenderung
from app.schemas.zeiterfassung import (
    ZEITERFASSUNG_BUCHUNGSSTATUS_LABEL,
    ZEITERFASSUNG_KATEGORIE_LABEL,
    ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT,
    ZeiterfassungAenderungRead,
    ZeiterfassungBuchungStornierenBody,
    ZeiterfassungIdsBody,
    ZeiterfassungManuellCreate,
    ZeiterfassungRead,
    ZeiterfassungStart,
    ZeiterfassungStatistik,
    ZeiterfassungStopBody,
    ZeiterfassungUpdate,
)
from app.services import papierkorb_service
from app.services.csv_service import csv_response
from app.services.event_bus import event_bus
from app.services.pdf_service import generate_wochenzettel_pdf
from app.services.rechte_service import (
    darf_fremde_mitarbeiterdaten_einsehen,
    darf_zeiten_buchen,
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


async def _mit_vorgangsnummern(
    session: AsyncSession, eintraege: list[Zeiterfassung]
) -> list[Zeiterfassung]:
    """Setzt das transiente ZeiterfassungRead.vorgangsnummer-Feld -- ein
    einzelner Batch-Lookup statt N+1, siehe gleiches Muster bei
    VorgangRead.zugewiesener_name in app/api/routes/vorgaenge.py."""
    vorgang_ids = {e.vorgang_id for e in eintraege if e.vorgang_id is not None}
    vorgaenge_by_id: dict[UUID, Vorgang] = {}
    for vorgang_id in vorgang_ids:
        vorgang = await session.get(Vorgang, vorgang_id)
        if vorgang is not None:
            vorgaenge_by_id[vorgang_id] = vorgang
    for eintrag in eintraege:
        vorgang = vorgaenge_by_id.get(eintrag.vorgang_id) if eintrag.vorgang_id else None
        eintrag.vorgangsnummer = vorgang.vorgangsnummer if vorgang else None
    return eintraege


def _jsonbar(wert: object) -> object:
    """JSONB-Spalten (alter_wert/neuer_wert) akzeptieren kein datetime/UUID/
    Decimal direkt -- der asyncpg-JSON-Codec kennt nur JSON-native Typen."""
    if isinstance(wert, datetime):
        return wert.isoformat()
    if isinstance(wert, UUID):
        return str(wert)
    if isinstance(wert, Decimal):
        return str(wert)
    return wert


def _protokoll(
    session: AsyncSession,
    *,
    mandant_id: UUID,
    zeiterfassung_id: UUID,
    aktion: str,
    feld: str | None = None,
    alter_wert: object | None = None,
    neuer_wert: object | None = None,
    grund: str | None = None,
    geaendert_von: UUID | None,
) -> None:
    session.add(
        ZeiterfassungAenderung(
            mandant_id=mandant_id,
            zeiterfassung_id=zeiterfassung_id,
            aktion=aktion,
            feld=feld,
            alter_wert=alter_wert,
            neuer_wert=neuer_wert,
            grund=grund,
            geaendert_von=geaendert_von,
        )
    )


@router.get("", response_model=list[ZeiterfassungRead])
async def list_zeiterfassung(
    vorgang_id: UUID | None = Query(default=None),
    techniker_id: UUID | None = Query(default=None),
    von: date | None = Query(default=None),
    bis: date | None = Query(default=None),
    buchungsstatus: str | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Zeiterfassung]:
    stmt = (
        select(Zeiterfassung)
        .where(Zeiterfassung.geloescht_am.is_(None))
        .order_by(Zeiterfassung.start_at.desc())
    )
    if buchungsstatus:
        stmt = stmt.where(Zeiterfassung.buchungsstatus == buchungsstatus)
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
    return await _mit_vorgangsnummern(session, list(result.scalars().all()))


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
    stmt = (
        select(Zeiterfassung)
        .where(Zeiterfassung.geloescht_am.is_(None))
        .order_by(Zeiterfassung.start_at.asc())
    )
    if techniker_id:
        stmt = stmt.where(Zeiterfassung.techniker_id == techniker_id)
    if von:
        stmt = stmt.where(Zeiterfassung.start_at >= _tagesbeginn(von))
    if bis:
        stmt = stmt.where(Zeiterfassung.start_at < _tagesbeginn(bis + timedelta(days=1)))
    eintraege = list((await session.execute(stmt)).scalars().all())

    technikers_by_id: dict[UUID, User | None] = {}
    vorgaenge_by_id: dict[UUID, Vorgang | None] = {}
    fahrzeuge_by_id: dict[UUID, Anlage | None] = {}
    rows = []
    for e in eintraege:
        if e.techniker_id not in technikers_by_id:
            technikers_by_id[e.techniker_id] = await session.get(User, e.techniker_id)
        techniker = technikers_by_id[e.techniker_id]
        vorgang = None
        if e.vorgang_id is not None:
            if e.vorgang_id not in vorgaenge_by_id:
                vorgaenge_by_id[e.vorgang_id] = await session.get(Vorgang, e.vorgang_id)
            vorgang = vorgaenge_by_id[e.vorgang_id]
        dauer_stunden = (
            (e.ende_at - e.start_at).total_seconds() / 3600 if e.ende_at else None
        )
        fahrzeug = None
        if e.fahrzeug_id is not None:
            if e.fahrzeug_id not in fahrzeuge_by_id:
                fahrzeuge_by_id[e.fahrzeug_id] = await session.get(Anlage, e.fahrzeug_id)
            fahrzeug = fahrzeuge_by_id[e.fahrzeug_id]
        rows.append(
            [
                e.start_at.strftime("%d.%m.%Y"),
                techniker.name if techniker else "",
                vorgang.vorgangsnummer if vorgang else "",
                ZEITERFASSUNG_KATEGORIE_LABEL.get(e.kategorie, "Auftrag"),
                e.taetigkeit or "",
                e.start_at.strftime("%H:%M"),
                e.ende_at.strftime("%H:%M") if e.ende_at else "",
                f"{dauer_stunden:.2f}".replace(".", ",") if dauer_stunden is not None else "",
                "Ja" if e.abrechenbar else "Nein",
                f"{e.km:.1f}".replace(".", ",") if e.km is not None else "",
                fahrzeug.bezeichnung if fahrzeug else "",
                ZEITERFASSUNG_BUCHUNGSSTATUS_LABEL.get(e.buchungsstatus, e.buchungsstatus),
            ]
        )

    return csv_response(
        [
            "Datum",
            "Techniker",
            "Vorgang",
            "Kategorie",
            "Tätigkeit",
            "Von",
            "Bis",
            "Dauer (Std.)",
            "Abrechenbar",
            "km",
            "Fahrzeug",
            "Status",
        ],
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
                Zeiterfassung.geloescht_am.is_(None),
                # Pause/Urlaub/Krankheit sind keine geleistete Arbeitszeit --
                # zaehlen bewusst nicht in die Stunden-Summen mit ein.
                Zeiterfassung.kategorie.notin_(ZEITERFASSUNG_KATEGORIEN_OHNE_ARBEITSZEIT),
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
            Zeiterfassung.geloescht_am.is_(None),
        )
        .order_by(Zeiterfassung.start_at)
    )
    eintraege = list(result.scalars().all())
    vorgaenge_by_id: dict[UUID, Vorgang | None] = {}
    for eintrag in eintraege:
        if eintrag.vorgang_id is not None and eintrag.vorgang_id not in vorgaenge_by_id:
            vorgaenge_by_id[eintrag.vorgang_id] = await session.get(Vorgang, eintrag.vorgang_id)
    paare = [
        (eintrag, vorgaenge_by_id.get(eintrag.vorgang_id) if eintrag.vorgang_id else None)
        for eintrag in eintraege
    ]

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
    eintrag = result.scalar_one_or_none()
    if eintrag is not None:
        await _mit_vorgangsnummern(session, [eintrag])
    return eintrag


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
        quelle="timer",
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
    _protokoll(
        session,
        mandant_id=auth.mandant_id,
        zeiterfassung_id=eintrag.id,
        aktion="angelegt",
        geaendert_von=auth.user_id,
    )
    await session.flush()

    await event_bus.publish(
        auth.mandant_id,
        "timer",
        {"vorgang_id": str(body.vorgang_id), "techniker_id": str(auth.user_id), "laeuft": True},
    )
    await _mit_vorgangsnummern(session, [eintrag])
    return eintrag


@router.post("/{zeiterfassung_id}/stop", response_model=ZeiterfassungRead)
async def stop_timer(
    zeiterfassung_id: UUID,
    body: ZeiterfassungStopBody = ZeiterfassungStopBody(),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Zeiterfassung:
    eintrag = await session.get(Zeiterfassung, zeiterfassung_id)
    if eintrag is None or eintrag.geloescht_am is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Zeiterfassung nicht gefunden"
        )
    ist_fremd = eintrag.techniker_id != auth.user_id
    if ist_fremd:
        # "Fremden laufenden Timer beenden" (Konzept 6.2/7.1) -- nur mit dem
        # Recht "Zeiten buchen", sonst wie gehabt "nicht gefunden" statt
        # 403, um nicht zu verraten, dass fuer diese ID ein fremder Eintrag
        # existiert.
        if not await darf_zeiten_buchen(session, role=auth.role, account_typ_id=auth.account_typ_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Zeiterfassung nicht gefunden"
            )
        if not body.grund or not body.grund.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Grund ist bei einem fremden Timer Pflicht",
            )
    if eintrag.ende_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Timer läuft nicht mehr"
        )

    # "Ende frei waehlbar" (Konzept 7.1) nur beim Beenden eines FREMDEN
    # Timers -- beim eigenen ist es immer "jetzt", wie bisher.
    if ist_fremd and body.ende_at is not None:
        ende = body.ende_at
    else:
        ende = datetime.now(timezone.utc)
    if ende <= eintrag.start_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Ende muss nach dem Start liegen"
        )
    _pruefe_zeitpunkt_nicht_in_zukunft(ende, feld="Ende")

    eintrag.ende_at = ende
    if ist_fremd:
        _protokoll(
            session,
            mandant_id=auth.mandant_id,
            zeiterfassung_id=eintrag.id,
            aktion="geaendert",
            feld="ende_at",
            neuer_wert=ende.isoformat(),
            grund=body.grund,
            geaendert_von=auth.user_id,
        )
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
        {"vorgang_id": str(eintrag.vorgang_id), "techniker_id": str(eintrag.techniker_id), "laeuft": False},
    )
    await _mit_vorgangsnummern(session, [eintrag])
    return eintrag


async def _lv_position_pruefen(
    session: AsyncSession, lv_position_id: UUID, vorgang: Vorgang | None
) -> None:
    """SVS-Kopplung: der gewaehlte Stundenverrechnungssatz muss ein
    ist_stundensatz-Eintrag sein und -- falls sein Leistungsverzeichnis
    ueberhaupt Kunden zugewiesen ist -- zum Kunden des Vorgangs gehoeren,
    sonst koennte man versehentlich den Satz eines fremden Kunden
    hinterlegen. Keine Zuweisung heisst "gilt fuer alle Kunden", siehe
    LeistungsverzeichnisKunde (die Kunden-Zuweisung sitzt am LV, nicht mehr
    an der einzelnen Position). RLS scopt session.get() bereits auf den
    eigenen Mandanten."""
    lv_position = await session.get(LeistungsverzeichnisPosition, lv_position_id)
    if lv_position is None or lv_position.geloescht_am is not None or not lv_position.ist_stundensatz:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stundenverrechnungssatz nicht gefunden",
        )
    if vorgang is not None:
        zugeordnete_kunden = (
            await session.execute(
                select(LeistungsverzeichnisKunde.kunde_id).where(
                    LeistungsverzeichnisKunde.leistungsverzeichnis_id == lv_position.leistungsverzeichnis_id
                )
            )
        ).scalars().all()
        if zugeordnete_kunden and vorgang.kunde_id not in zugeordnete_kunden:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stundenverrechnungssatz gehört nicht zum Kunden dieses Vorgangs",
            )


# Enger als VORGANG_STATUS_GESCHLOSSEN (das zusaetzlich "abgeschlossen"
# enthaelt): Nachtragen/Bearbeiten von Zeit soll nach Abschluss eines
# Vorgangs weiterhin moeglich sein (genau der Anwendungsfall "Tätigkeit
# nachtragen"), nur nicht mehr nach Abrechnung/Stornierung. Der Timer
# selbst bleibt ueber VORGANG_STATUS_GESCHLOSSEN bei "abgeschlossen" schon
# gesperrt (siehe start_timer oben).
_VORGANG_STATUS_ZEIT_GESPERRT = frozenset({"abgerechnet", "storniert"})

_ZUKUNFT_TOLERANZ = timedelta(minutes=2)


def _pruefe_zeitpunkt_nicht_in_zukunft(zeitpunkt: datetime | None, *, feld: str = "Start") -> None:
    # Bei Erfassen/Bearbeiten wird nur der Start geprueft, nicht das Ende:
    # ein bereits begonnener Eintrag (z.B. "Urlaub ab jetzt, ganzer Tag")
    # endet legitim erst spaeter am selben Tag -- das Ende darf also in der
    # (nahen) Zukunft liegen (siehe test_zeiterfassung_manuell.py:
    # test_manueller_eintrag_ohne_vorgang). Beim Beenden eines fremden
    # Timers mit frei waehlbarem Ende (Konzept 7.1) rueft dieselbe Funktion
    # stattdessen das Ende -- daher das parametrisierte feld fuer die
    # Fehlermeldung.
    grenze = datetime.now(timezone.utc) + _ZUKUNFT_TOLERANZ
    if zeitpunkt is not None and zeitpunkt > grenze:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{feld} darf nicht in der Zukunft liegen",
        )


def _pruefe_vorgang_nicht_gesperrt(vorgang: Vorgang) -> None:
    if vorgang.status in _VORGANG_STATUS_ZEIT_GESPERRT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vorgang ist abgerechnet oder storniert und kann nicht mehr bebucht werden",
        )


def _pruefe_fahrt_felder(kategorie: str, km: Decimal | None, fahrzeug_id: UUID | None) -> None:
    """km/fahrzeug_id sind nur bei kategorie='fahrzeit' sinnvoll (Konzept
    Abschnitt 11) -- die Pruefung sitzt hier statt als DB-CHECK, weil sich
    die Kategorie per PATCH aendern kann (siehe Migration 0085)."""
    if kategorie != "fahrzeit" and (km is not None or fahrzeug_id is not None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="km/Fahrzeug sind nur bei Kategorie 'fahrzeit' erlaubt",
        )


async def _fahrzeug_pruefen(session: AsyncSession, fahrzeug_id: UUID) -> None:
    anlage = await session.get(Anlage, fahrzeug_id)
    if anlage is None or anlage.geloescht_am is not None or anlage.objekttyp != "fahrzeug":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Fahrzeug nicht gefunden")


async def _vorgang_pruefen_fuer_manuellen_eintrag(
    session: AsyncSession, auth: AuthContext, vorgang_id: UUID
) -> Vorgang:
    vorgang = await session.get(Vorgang, vorgang_id)
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
    _pruefe_vorgang_nicht_gesperrt(vorgang)
    return vorgang


@router.post(
    "/manuell",
    response_model=ZeiterfassungRead,
    status_code=status.HTTP_201_CREATED,
)
async def manuellen_eintrag_anlegen(
    body: ZeiterfassungManuellCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Zeiterfassung:
    # "auftrag" ohne Vorgangsbezug waere fuer Auswertung/Wochenzettel
    # bedeutungslos (keine Vorgangsnummer zum Anzeigen) -- alle anderen
    # Kategorien duerfen bewusst ohne Vorgang stehen.
    if body.kategorie == "auftrag" and body.vorgang_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kategorie 'auftrag' braucht einen Vorgang",
        )
    ziel_techniker_id = auth.user_id
    if body.techniker_id is not None and body.techniker_id != auth.user_id:
        # "Fuer einen anderen nachtragen" (Konzept 6.2) -- nur mit dem Recht
        # "Zeiten buchen". Der neue Eintrag startet trotzdem als 'vermerkt',
        # nachtragen ersetzt das Vormerken/Buchen nicht.
        if not await darf_zeiten_buchen(session, role=auth.role, account_typ_id=auth.account_typ_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nur mit dem Recht 'Zeiten buchen' für andere nachtragbar",
            )
        ziel_user = await session.get(User, body.techniker_id)
        if ziel_user is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Techniker nicht gefunden")
        ziel_techniker_id = body.techniker_id

    vorgang = None
    if body.vorgang_id is not None:
        vorgang = await _vorgang_pruefen_fuer_manuellen_eintrag(session, auth, body.vorgang_id)
    if body.lv_position_id is not None:
        await _lv_position_pruefen(session, body.lv_position_id, vorgang)
    _pruefe_fahrt_felder(body.kategorie, body.km, body.fahrzeug_id)
    if body.fahrzeug_id is not None:
        await _fahrzeug_pruefen(session, body.fahrzeug_id)

    eintrag = Zeiterfassung(
        mandant_id=auth.mandant_id,
        vorgang_id=body.vorgang_id,
        techniker_id=ziel_techniker_id,
        start_at=body.start_at,
        ende_at=body.ende_at,
        taetigkeit=body.taetigkeit,
        abrechenbar=body.abrechenbar,
        kategorie=body.kategorie,
        lv_position_id=body.lv_position_id,
        km=body.km,
        fahrzeug_id=body.fahrzeug_id,
        quelle="manuell",
    )
    session.add(eintrag)
    await session.flush()
    _protokoll(
        session,
        mandant_id=auth.mandant_id,
        zeiterfassung_id=eintrag.id,
        aktion="angelegt",
        geaendert_von=auth.user_id,
    )
    await session.flush()
    await session.refresh(eintrag)
    await _mit_vorgangsnummern(session, [eintrag])
    return eintrag


# Nur in diesem Status darf ein Eintrag per PATCH/DELETE veraendert werden
# (Konzept 6.2) -- vorgemerkt muss erst zurueckgezogen, gebucht erst
# storniert werden, abgerechnet ist endgueltig gesperrt.
_BUCHUNGSSTATUS_BEARBEITBAR = "vermerkt"


def _pruefe_buchungsstatus_bearbeitbar(eintrag: Zeiterfassung) -> None:
    if eintrag.buchungsstatus != _BUCHUNGSSTATUS_BEARBEITBAR:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Eintrag ist '{eintrag.buchungsstatus}' und muss dafür erst "
                "zurückgezogen bzw. storniert werden"
            ),
        )


@router.patch("/{zeiterfassung_id}", response_model=ZeiterfassungRead)
async def zeiterfassung_aktualisieren(
    zeiterfassung_id: UUID,
    body: ZeiterfassungUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Zeiterfassung:
    eintrag = await session.get(Zeiterfassung, zeiterfassung_id)
    if eintrag is None or eintrag.geloescht_am is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Zeiterfassung nicht gefunden"
        )

    ist_fremd = eintrag.techniker_id != auth.user_id
    if ist_fremd and not await darf_zeiten_buchen(
        session, role=auth.role, account_typ_id=auth.account_typ_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Zeiterfassung nicht gefunden"
        )

    daten = body.model_dump(exclude_unset=True, exclude={"grund"})

    if eintrag.ende_at is None:
        # Laufender Timer: nur die Taetigkeit darf nachgetragen werden
        # (siehe docs/konzepte/ZEITERFASSUNG.md, Stufe 1) -- Start/Ende
        # weiterhin ausschliesslich ueber "stop", damit kein Timer per PATCH
        # unbemerkt "beendet" wird. Ein fremder laufender Timer wird nur
        # ueber /stop beendet (Stufe 2), nicht hier bearbeitet.
        if ist_fremd:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ein fremder laufender Timer wird über 'stop' beendet, nicht bearbeitet",
            )
        if set(daten) - {"taetigkeit"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ein laufender Timer wird über 'stop' beendet, nicht über diese Route",
            )
        if "taetigkeit" in daten and daten["taetigkeit"] != eintrag.taetigkeit:
            _protokoll(
                session,
                mandant_id=auth.mandant_id,
                zeiterfassung_id=eintrag.id,
                aktion="geaendert",
                feld="taetigkeit",
                alter_wert=eintrag.taetigkeit,
                neuer_wert=daten["taetigkeit"],
                geaendert_von=auth.user_id,
            )
            eintrag.taetigkeit = daten["taetigkeit"]
        await session.flush()
        await session.refresh(eintrag)
        await _mit_vorgangsnummern(session, [eintrag])
        return eintrag

    _pruefe_buchungsstatus_bearbeitbar(eintrag)
    if ist_fremd and (not body.grund or not body.grund.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Grund ist beim Bearbeiten eines fremden Eintrags Pflicht",
        )

    neue_kategorie = daten.get("kategorie", eintrag.kategorie)
    neuer_vorgang_id = daten.get("vorgang_id", eintrag.vorgang_id)
    if neue_kategorie == "auftrag" and neuer_vorgang_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kategorie 'auftrag' braucht einen Vorgang",
        )
    neuer_vorgang = None
    if "vorgang_id" in daten and daten["vorgang_id"] is not None:
        neuer_vorgang = await _vorgang_pruefen_fuer_manuellen_eintrag(session, auth, daten["vorgang_id"])
    elif eintrag.vorgang_id is not None:
        bestehender_vorgang = await session.get(Vorgang, eintrag.vorgang_id)
        if bestehender_vorgang is not None:
            _pruefe_vorgang_nicht_gesperrt(bestehender_vorgang)
    if "lv_position_id" in daten and daten["lv_position_id"] is not None:
        if neuer_vorgang is None and eintrag.vorgang_id is not None:
            neuer_vorgang = await session.get(Vorgang, eintrag.vorgang_id)
        await _lv_position_pruefen(session, daten["lv_position_id"], neuer_vorgang)

    neue_km = daten.get("km", eintrag.km)
    neuer_fahrzeug_id = daten.get("fahrzeug_id", eintrag.fahrzeug_id)
    _pruefe_fahrt_felder(neue_kategorie, neue_km, neuer_fahrzeug_id)
    if "fahrzeug_id" in daten and daten["fahrzeug_id"] is not None:
        await _fahrzeug_pruefen(session, daten["fahrzeug_id"])

    neuer_start = daten.get("start_at", eintrag.start_at)
    neues_ende = daten.get("ende_at", eintrag.ende_at)
    if neues_ende is not None and neues_ende <= neuer_start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Ende muss nach dem Start liegen"
        )
    _pruefe_zeitpunkt_nicht_in_zukunft(neuer_start)

    for feld, wert in daten.items():
        alter_wert = getattr(eintrag, feld)
        if alter_wert == wert:
            continue
        _protokoll(
            session,
            mandant_id=auth.mandant_id,
            zeiterfassung_id=eintrag.id,
            aktion="geaendert",
            feld=feld,
            alter_wert=_jsonbar(alter_wert),
            neuer_wert=_jsonbar(wert),
            grund=body.grund if ist_fremd else None,
            geaendert_von=auth.user_id,
        )
        setattr(eintrag, feld, wert)
    await session.flush()
    await session.refresh(eintrag)
    await _mit_vorgangsnummern(session, [eintrag])
    return eintrag


@router.delete("/{zeiterfassung_id}", status_code=status.HTTP_204_NO_CONTENT)
async def zeiterfassung_loeschen(
    zeiterfassung_id: UUID,
    grund: str | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    eintrag = await session.get(Zeiterfassung, zeiterfassung_id)
    if eintrag is None or eintrag.geloescht_am is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Zeiterfassung nicht gefunden"
        )
    ist_fremd = eintrag.techniker_id != auth.user_id
    if ist_fremd and not await darf_zeiten_buchen(
        session, role=auth.role, account_typ_id=auth.account_typ_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Zeiterfassung nicht gefunden"
        )
    if ist_fremd and (not grund or not grund.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Grund ist beim Löschen eines fremden Eintrags Pflicht",
        )
    _pruefe_buchungsstatus_bearbeitbar(eintrag)
    if eintrag.vorgang_id is not None:
        vorgang = await session.get(Vorgang, eintrag.vorgang_id)
        if vorgang is not None:
            _pruefe_vorgang_nicht_gesperrt(vorgang)
    await papierkorb_service.soft_delete(
        session, entity_typ="zeiterfassung", entity_id=zeiterfassung_id, actor_user_id=auth.user_id
    )
    _protokoll(
        session,
        mandant_id=auth.mandant_id,
        zeiterfassung_id=eintrag.id,
        aktion="geloescht",
        grund=grund if ist_fremd else None,
        geaendert_von=auth.user_id,
    )
    await session.flush()


async def _eintraege_laden(session: AsyncSession, ids: list[UUID]) -> dict[UUID, Zeiterfassung]:
    if not ids:
        return {}
    result = await session.execute(
        select(Zeiterfassung).where(Zeiterfassung.id.in_(ids), Zeiterfassung.geloescht_am.is_(None))
    )
    return {e.id: e for e in result.scalars().all()}


async def _vorgang_gesperrt_fuer(session: AsyncSession, eintrag: Zeiterfassung) -> bool:
    if eintrag.vorgang_id is None:
        return False
    vorgang = await session.get(Vorgang, eintrag.vorgang_id)
    return vorgang is not None and vorgang.status in _VORGANG_STATUS_ZEIT_GESPERRT


@router.post("/vormerken", response_model=list[ZeiterfassungRead])
async def zeiterfassung_vormerken(
    body: ZeiterfassungIdsBody,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Zeiterfassung]:
    """vermerkt -> vorgemerkt (Konzept 6.1). Jeder fuer eigene Eintraege,
    Buchungsberechtigte fuer beliebige. Alles oder nichts: scheitert die
    Pruefung bei einem Eintrag, wird keiner vorgemerkt."""
    berechtigt = await darf_zeiten_buchen(session, role=auth.role, account_typ_id=auth.account_typ_id)
    eintraege = await _eintraege_laden(session, body.ids)
    fehler: list[str] = []
    for eid in body.ids:
        e = eintraege.get(eid)
        if e is None:
            fehler.append(f"{eid} (nicht gefunden)")
        elif not berechtigt and e.techniker_id != auth.user_id:
            fehler.append(f"{eid} (nicht deine Zeit)")
        elif e.buchungsstatus != "vermerkt":
            fehler.append(f"{eid} (Status: {e.buchungsstatus})")
        elif e.ende_at is None:
            fehler.append(f"{eid} (Timer läuft noch)")
        elif not e.taetigkeit or not e.taetigkeit.strip():
            fehler.append(f"{eid} (Tätigkeit fehlt)")
        elif e.vorgang_id is None:
            fehler.append(f"{eid} (ohne Vorgang nicht vormerkbar)")
        elif await _vorgang_gesperrt_fuer(session, e):
            fehler.append(f"{eid} (Vorgang gesperrt)")
    if fehler:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Nicht vormerkbar: " + "; ".join(fehler)
        )

    jetzt = datetime.now(timezone.utc)
    ergebnis = []
    for eid in body.ids:
        e = eintraege[eid]
        e.buchungsstatus = "vorgemerkt"
        e.vorgemerkt_von = auth.user_id
        e.vorgemerkt_am = jetzt
        _protokoll(
            session,
            mandant_id=auth.mandant_id,
            zeiterfassung_id=e.id,
            aktion="vorgemerkt",
            geaendert_von=auth.user_id,
        )
        ergebnis.append(e)
    await session.flush()
    for e in ergebnis:
        await session.refresh(e)
    await _mit_vorgangsnummern(session, ergebnis)
    return ergebnis


@router.post("/vormerkung-zurueckziehen", response_model=list[ZeiterfassungRead])
async def zeiterfassung_vormerkung_zurueckziehen(
    body: ZeiterfassungIdsBody,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Zeiterfassung]:
    """vorgemerkt -> vermerkt (Konzept 6.1). Jeder fuer eigene Eintraege,
    Buchungsberechtigte fuer beliebige."""
    berechtigt = await darf_zeiten_buchen(session, role=auth.role, account_typ_id=auth.account_typ_id)
    eintraege = await _eintraege_laden(session, body.ids)
    fehler: list[str] = []
    for eid in body.ids:
        e = eintraege.get(eid)
        if e is None:
            fehler.append(f"{eid} (nicht gefunden)")
        elif not berechtigt and e.techniker_id != auth.user_id:
            fehler.append(f"{eid} (nicht deine Zeit)")
        elif e.buchungsstatus != "vorgemerkt":
            fehler.append(f"{eid} (Status: {e.buchungsstatus})")
    if fehler:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nicht zurückziehbar: " + "; ".join(fehler),
        )

    ergebnis = []
    for eid in body.ids:
        e = eintraege[eid]
        e.buchungsstatus = "vermerkt"
        e.vorgemerkt_von = None
        e.vorgemerkt_am = None
        _protokoll(
            session,
            mandant_id=auth.mandant_id,
            zeiterfassung_id=e.id,
            aktion="vormerkung_zurueckgezogen",
            geaendert_von=auth.user_id,
        )
        ergebnis.append(e)
    await session.flush()
    for e in ergebnis:
        await session.refresh(e)
    await _mit_vorgangsnummern(session, ergebnis)
    return ergebnis


@router.post("/buchen", response_model=list[ZeiterfassungRead])
async def zeiterfassung_buchen(
    body: ZeiterfassungIdsBody,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Zeiterfassung]:
    """vermerkt|vorgemerkt -> gebucht (Konzept 6.1) -- direktes Buchen aus
    'vermerkt' erspart das Vormerken, auch fuer eigene Eintraege. Nur mit
    dem Recht 'Zeiten buchen'."""
    if not await darf_zeiten_buchen(session, role=auth.role, account_typ_id=auth.account_typ_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Recht 'Zeiten buchen' erforderlich"
        )
    eintraege = await _eintraege_laden(session, body.ids)
    fehler: list[str] = []
    for eid in body.ids:
        e = eintraege.get(eid)
        if e is None:
            fehler.append(f"{eid} (nicht gefunden)")
        elif e.buchungsstatus not in ("vermerkt", "vorgemerkt"):
            fehler.append(f"{eid} (Status: {e.buchungsstatus})")
        elif e.ende_at is None:
            fehler.append(f"{eid} (Timer läuft noch)")
        elif not e.taetigkeit or not e.taetigkeit.strip():
            fehler.append(f"{eid} (Tätigkeit fehlt)")
        elif e.vorgang_id is None:
            fehler.append(f"{eid} (ohne Vorgang nicht buchbar)")
        elif await _vorgang_gesperrt_fuer(session, e):
            fehler.append(f"{eid} (Vorgang gesperrt)")
    if fehler:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Nicht buchbar: " + "; ".join(fehler)
        )

    jetzt = datetime.now(timezone.utc)
    ergebnis = []
    for eid in body.ids:
        e = eintraege[eid]
        e.buchungsstatus = "gebucht"
        e.gebucht_von = auth.user_id
        e.gebucht_am = jetzt
        _protokoll(
            session,
            mandant_id=auth.mandant_id,
            zeiterfassung_id=e.id,
            aktion="gebucht",
            geaendert_von=auth.user_id,
        )
        ergebnis.append(e)
    await session.flush()
    for e in ergebnis:
        await session.refresh(e)
    await _mit_vorgangsnummern(session, ergebnis)
    return ergebnis


@router.post("/buchung-stornieren", response_model=list[ZeiterfassungRead])
async def zeiterfassung_buchung_stornieren(
    body: ZeiterfassungBuchungStornierenBody,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Zeiterfassung]:
    """gebucht -> vermerkt (Konzept 6.1) -- Grund ist Pflicht. Nur mit dem
    Recht 'Zeiten buchen', auch fuer selbst gebuchte Eintraege (die sind
    sonst fuer niemanden mehr aenderbar, siehe Konzept 6.2)."""
    if not await darf_zeiten_buchen(session, role=auth.role, account_typ_id=auth.account_typ_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Recht 'Zeiten buchen' erforderlich"
        )
    if not body.grund.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Grund ist Pflicht")
    eintraege = await _eintraege_laden(session, body.ids)
    fehler: list[str] = []
    for eid in body.ids:
        e = eintraege.get(eid)
        if e is None:
            fehler.append(f"{eid} (nicht gefunden)")
        elif e.buchungsstatus != "gebucht":
            fehler.append(f"{eid} (Status: {e.buchungsstatus})")
    if fehler:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Buchung nicht stornierbar: " + "; ".join(fehler),
        )

    ergebnis = []
    for eid in body.ids:
        e = eintraege[eid]
        e.buchungsstatus = "vermerkt"
        e.gebucht_von = None
        e.gebucht_am = None
        e.vorgemerkt_von = None
        e.vorgemerkt_am = None
        _protokoll(
            session,
            mandant_id=auth.mandant_id,
            zeiterfassung_id=e.id,
            aktion="buchung_storniert",
            grund=body.grund,
            geaendert_von=auth.user_id,
        )
        ergebnis.append(e)
    await session.flush()
    for e in ergebnis:
        await session.refresh(e)
    await _mit_vorgangsnummern(session, ergebnis)
    return ergebnis


@router.get("/{zeiterfassung_id}/verlauf", response_model=list[ZeiterfassungAenderungRead])
async def zeiterfassung_verlauf(
    zeiterfassung_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[ZeiterfassungAenderung]:
    eintrag = await session.get(Zeiterfassung, zeiterfassung_id)
    if eintrag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Zeiterfassung nicht gefunden"
        )
    if eintrag.techniker_id != auth.user_id and not await darf_zeiten_buchen(
        session, role=auth.role, account_typ_id=auth.account_typ_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Zeiterfassung nicht gefunden"
        )
    result = await session.execute(
        select(ZeiterfassungAenderung)
        .where(ZeiterfassungAenderung.zeiterfassung_id == zeiterfassung_id)
        .order_by(ZeiterfassungAenderung.geaendert_am.desc())
    )
    return list(result.scalars().all())
