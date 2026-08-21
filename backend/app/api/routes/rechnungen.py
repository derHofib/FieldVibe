from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AuthContext,
    get_current_user,
    get_db,
    require_module,
    require_recht,
    require_roles,
)
from app.models.email_log import EmailLog
from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.rechnung import RECHNUNG_ZAHLUNGSARTEN, Rechnung, RechnungPosition, RechnungZahlung
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.email import EmailLogRead, EmailMitAnhangSenden
from app.schemas.rechnung import (
    RechnungCreate,
    RechnungListe,
    RechnungPositionCreate,
    RechnungPositionVorschlag,
    RechnungRead,
    RechnungUpdate,
    RechnungZahlungCreate,
)
from app.services import papierkorb_service, storage_service
from app.services.csv_service import csv_response
from app.services.email_service import send_email_and_log
from app.services.numbering_service import next_rechnungsnummer
from app.services.rechnung_service import (
    archiviere_pdf,
    bezahlter_betrag,
    brutto_betrag,
    brutto_sql,
    erstelle_stornorechnung,
    kunden_namen_fuer,
    netto_sql,
    offen_sql,
    pdf_bytes_fuer,
    positionen_fuer,
    positionen_vorschlaege_fuer_vorgang,
    status_nach_zahlung,
    to_read_model,
    to_read_model_bulk,
    zahlungen_fuer,
)

router = APIRouter(
    prefix="/api/rechnungen",
    tags=["rechnungen"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_module("abrechnung")),
        Depends(require_recht("abrechnung", "sehen")),
    ],
)

_GUELTIGE_UEBERGAENGE = {
    "entwurf": {"versendet", "storniert"},
    # "storniert" ist ab "versendet" bewusst NICHT mehr per einfachem
    # Status-Flip erreichbar -- eine bereits versendete Rechnung darf GoBD-
    # konform nicht einfach umgeschrieben werden, dafuer gibt es den eigenen
    # Endpunkt POST /{id}/storno (siehe erstelle_stornorechnung).
    "versendet": {"bezahlt"},
    # "teilweise_bezahlt" ist nie Ziel eines PATCH-Uebergangs -- es ist ein
    # abgeleiteter Zustand, den ausschliesslich POST /{id}/zahlungen setzt
    # (siehe status_nach_zahlung). "bezahlt" bleibt hier als manueller
    # Notausgang ("Rest ist abgehakt") erreichbar.
    "teilweise_bezahlt": {"bezahlt"},
}


async def _storniert_rechnung_fuer(session: AsyncSession, rechnung: Rechnung) -> Rechnung | None:
    if rechnung.storniert_rechnung_id is None:
        return None
    return await session.get(Rechnung, rechnung.storniert_rechnung_id)


# Statuswerte, bei denen noch Geld aussteht -- Grundlage fuer "nur_offen",
# "nur_ueberfaellig" und die Spalte summe_offen der Uebersicht.
_OFFENE_STATUS = ("entwurf", "versendet", "teilweise_bezahlt")

# Sortierschluessel der Uebersicht. Ein "-" davor kehrt die Richtung um.
# brutto_sql() statt einer Spalte, weil Brutto nirgends persistiert ist.
_SORTIERBAR = {
    "datum": lambda: Rechnung.created_at,
    "faellig": lambda: Rechnung.faellig_am,
    "betrag": brutto_sql,
    "nummer": lambda: Rechnung.rechnungsnummer,
}


def _filter_bedingungen(
    kunde_id: UUID | None,
    vorgang_id: UUID | None,
    status_filter: list[str] | None,
    q: str | None,
    von: date | None,
    bis: date | None,
    faellig_von: date | None,
    faellig_bis: date | None,
    betrag_von: Decimal | None,
    betrag_bis: Decimal | None,
    nur_offen: bool,
    nur_ueberfaellig: bool,
) -> list:
    """Die Filter einmal bauen und sowohl auf die Seiten- als auch auf die
    Summen-Query anwenden, damit Summenzeile und Liste nie auseinanderlaufen."""
    bedingungen = [Rechnung.geloescht_am.is_(None)]
    if kunde_id:
        bedingungen.append(Rechnung.kunde_id == kunde_id)
    if vorgang_id:
        bedingungen.append(Rechnung.vorgang_id == vorgang_id)
    if status_filter:
        bedingungen.append(Rechnung.status.in_(status_filter))
    if q:
        # Kundenname per Subquery statt Join -- so bleibt die Query auch fuer
        # die Summen-Aggregation unveraendert einsetzbar.
        muster = f"%{q}%"
        passende_kunden = select(Kunde.id).where(Kunde.name.ilike(muster)).scalar_subquery()
        bedingungen.append(
            or_(Rechnung.rechnungsnummer.ilike(muster), Rechnung.kunde_id.in_(passende_kunden))
        )
    if von:
        bedingungen.append(func.date(Rechnung.created_at) >= von)
    if bis:
        bedingungen.append(func.date(Rechnung.created_at) <= bis)
    if faellig_von:
        bedingungen.append(Rechnung.faellig_am >= faellig_von)
    if faellig_bis:
        bedingungen.append(Rechnung.faellig_am <= faellig_bis)
    if betrag_von is not None:
        bedingungen.append(brutto_sql() >= betrag_von)
    if betrag_bis is not None:
        bedingungen.append(brutto_sql() <= betrag_bis)
    if nur_offen and not nur_ueberfaellig:
        bedingungen.append(Rechnung.status.in_(_OFFENE_STATUS))
    if nur_ueberfaellig:
        # Bewusst enger als _OFFENE_STATUS: ein Entwurf ist nie ueberfaellig,
        # weil er den Kunden nie erreicht hat. Muss deckungsgleich mit
        # RechnungRead.ist_ueberfaellig bleiben, sonst liefert der Filter
        # Zeilen, die sich selbst als "nicht ueberfaellig" ausweisen.
        bedingungen.append(Rechnung.status == "versendet")
        bedingungen.append(Rechnung.faellig_am.is_not(None))
        bedingungen.append(Rechnung.faellig_am < date.today())
    return bedingungen


@router.get("", response_model=RechnungListe)
async def list_rechnungen(
    kunde_id: UUID | None = Query(default=None),
    vorgang_id: UUID | None = Query(default=None),
    status_filter: list[str] | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, description="Rechnungsnummer oder Kundenname"),
    von: date | None = Query(default=None, description="Rechnungsdatum ab"),
    bis: date | None = Query(default=None, description="Rechnungsdatum bis"),
    faellig_von: date | None = Query(default=None),
    faellig_bis: date | None = Query(default=None),
    betrag_von: Decimal | None = Query(default=None, description="Bruttobetrag ab"),
    betrag_bis: Decimal | None = Query(default=None, description="Bruttobetrag bis"),
    nur_offen: bool = Query(default=False),
    nur_ueberfaellig: bool = Query(default=False),
    sort: str = Query(default="-datum"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> RechnungListe:
    bedingungen = _filter_bedingungen(
        kunde_id,
        vorgang_id,
        status_filter,
        q,
        von,
        bis,
        faellig_von,
        faellig_bis,
        betrag_von,
        betrag_bis,
        nur_offen,
        nur_ueberfaellig,
    )

    absteigend = sort.startswith("-")
    schluessel = sort.lstrip("-")
    if schluessel not in _SORTIERBAR:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unbekannter Sortierschlüssel '{schluessel}' "
            f"(erlaubt: {', '.join(sorted(_SORTIERBAR))})",
        )
    spalte = _SORTIERBAR[schluessel]()
    richtung = spalte.desc() if absteigend else spalte.asc()
    # nulls_last: Rechnungen ohne Faelligkeit sollen die Sortierung nicht
    # anfuehren. Rechnung.id als Tiebreaker, sonst wackelt die Seitengrenze
    # bei gleichen Sortierwerten und Zeilen erscheinen doppelt oder fehlen.
    sortierung = (richtung.nulls_last(), Rechnung.id.asc())

    seite = await session.execute(
        select(Rechnung).where(*bedingungen).order_by(*sortierung).limit(limit).offset(offset)
    )
    rechnungen = list(seite.scalars().all())

    # offen_sql() statt einer festen "voller Betrag oder 0"-Fallunterscheidung,
    # sonst zaehlt eine teilweise_bezahlt-Rechnung mit dem vollen Bruttobetrag
    # statt dem tatsaechlich noch offenen Rest.
    offen_wenn_unbezahlt = case(
        (Rechnung.status.in_(_OFFENE_STATUS), offen_sql()), else_=Decimal("0")
    )
    summen = (
        await session.execute(
            select(
                func.count(Rechnung.id),
                func.coalesce(func.sum(netto_sql()), Decimal("0")),
                func.coalesce(func.sum(brutto_sql()), Decimal("0")),
                func.coalesce(func.sum(offen_wenn_unbezahlt), Decimal("0")),
            ).where(*bedingungen)
        )
    ).one()

    return RechnungListe(
        eintraege=await to_read_model_bulk(session, rechnungen),
        gesamt_anzahl=summen[0],
        summe_netto=summen[1],
        summe_brutto=summen[2],
        summe_offen=summen[3],
    )


# Muss VOR "/{rechnung_id}" stehen, sonst versucht FastAPI "export" als UUID
# zu parsen und antwortet mit 422 statt mit der CSV.
@router.get("/export/csv")
async def export_rechnungen_csv(
    kunde_id: UUID | None = Query(default=None),
    vorgang_id: UUID | None = Query(default=None),
    status_filter: list[str] | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    von: date | None = Query(default=None),
    bis: date | None = Query(default=None),
    faellig_von: date | None = Query(default=None),
    faellig_bis: date | None = Query(default=None),
    betrag_von: Decimal | None = Query(default=None),
    betrag_bis: Decimal | None = Query(default=None),
    nur_offen: bool = Query(default=False),
    nur_ueberfaellig: bool = Query(default=False),
    session: AsyncSession = Depends(get_db),
) -> Response:
    bedingungen = _filter_bedingungen(
        kunde_id,
        vorgang_id,
        status_filter,
        q,
        von,
        bis,
        faellig_von,
        faellig_bis,
        betrag_von,
        betrag_bis,
        nur_offen,
        nur_ueberfaellig,
    )
    result = await session.execute(
        select(Rechnung).where(*bedingungen).order_by(Rechnung.created_at.desc(), Rechnung.id.asc())
    )
    rechnungen = list(result.scalars().all())
    gelesen = await to_read_model_bulk(session, rechnungen)

    kunden_namen = await kunden_namen_fuer(session, [r.kunde_id for r in rechnungen])
    rows = [
        [
            r.rechnungsnummer,
            kunden_namen.get(r.kunde_id, ""),
            r.created_at.strftime("%d.%m.%Y"),
            r.leistungsdatum.strftime("%d.%m.%Y") if r.leistungsdatum else "",
            r.faellig_am.strftime("%d.%m.%Y") if r.faellig_am else "",
            r.status,
            str(r.betrag_netto),
            str(r.mwst_satz),
            str(r.betrag_brutto),
            str(r.tage_ueberfaellig),
            str(r.mahnstufe),
        ]
        for r in gelesen
    ]
    return csv_response(
        [
            "Rechnungsnummer",
            "Kunde",
            "Rechnungsdatum",
            "Leistungsdatum",
            "Fällig am",
            "Status",
            "Netto",
            "MwSt-Satz",
            "Brutto",
            "Tage überfällig",
            "Mahnstufe",
        ],
        rows,
        "Rechnungen.csv",
    )


@router.get("/{rechnung_id}", response_model=RechnungRead)
async def get_rechnung(rechnung_id: UUID, session: AsyncSession = Depends(get_db)) -> RechnungRead:
    rechnung = await session.get(Rechnung, rechnung_id)
    if rechnung is None or rechnung.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rechnung nicht gefunden")
    return await to_read_model(session, rechnung)


@router.delete(
    "/{rechnung_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("abrechnung", "loeschen")),
    ],
)
async def delete_rechnung(
    rechnung_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    rechnung = await session.get(Rechnung, rechnung_id)
    if rechnung is None or rechnung.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rechnung nicht gefunden")
    if rechnung.status != "entwurf":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nur Rechnungen im Entwurf können gelöscht werden",
        )
    await papierkorb_service.soft_delete(
        session, entity_typ="rechnung", entity_id=rechnung_id, actor_user_id=auth.user_id
    )


def _neue_positionen(
    rechnung_id: UUID, mandant_id: UUID, eintraege: list[RechnungPositionCreate]
) -> list[RechnungPosition]:
    return [
        RechnungPosition(
            mandant_id=mandant_id,
            rechnung_id=rechnung_id,
            position=i + 1,
            beschreibung=e.beschreibung,
            menge=e.menge,
            einheit=e.einheit,
            einzelpreis=e.einzelpreis,
        )
        for i, e in enumerate(eintraege)
    ]


@router.post(
    "",
    response_model=RechnungRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("abrechnung", "erstellen")),
    ],
)
async def create_rechnung(
    body: RechnungCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RechnungRead:
    if await session.get(Kunde, body.kunde_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kunde nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    vorgang = None
    if body.vorgang_id is not None:
        vorgang = await session.get(Vorgang, body.vorgang_id)
        if vorgang is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )
        if vorgang.kunde_id != body.kunde_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Vorgang gehört nicht zum angegebenen Kunden"
            )

    mandant = await session.get(Mandant, auth.mandant_id)
    # Kleinunternehmer (§19 UStG) duerfen keine Umsatzsteuer ausweisen -- der
    # Satz wird hier serverseitig erzwungen, damit kein Aufruf (versehentlich
    # oder nicht) trotzdem eine besteuerte Rechnung erzeugen kann.
    ist_kleinunternehmer = bool((mandant.firmendaten or {}).get("ist_kleinunternehmer"))
    mwst_satz = Decimal("0") if ist_kleinunternehmer else body.mwst_satz

    rechnungsnummer = await next_rechnungsnummer(session, auth.mandant_id)
    rechnung = Rechnung(
        mandant_id=auth.mandant_id,
        kunde_id=body.kunde_id,
        vorgang_id=body.vorgang_id,
        rechnungsnummer=rechnungsnummer,
        betrag_netto=body.betrag_netto,
        mwst_satz=mwst_satz,
        faellig_am=body.faellig_am,
        leistungsdatum=body.leistungsdatum,
        erstellt_von=auth.user_id,
    )
    session.add(rechnung)
    await session.flush()

    for p in _neue_positionen(rechnung.id, auth.mandant_id, body.positionen):
        session.add(p)
    await session.flush()
    await session.refresh(rechnung)

    if vorgang is not None:
        session.add(
            VorgangEvent(
                mandant_id=auth.mandant_id,
                vorgang_id=vorgang.id,
                event_type="rechnung_status",
                author_user_id=auth.user_id,
                body=f"Rechnung {rechnungsnummer} erstellt (Entwurf)",
                payload={"rechnung_id": str(rechnung.id), "status": "entwurf"},
            )
        )
        await session.flush()
    return await to_read_model(session, rechnung)


@router.post(
    "/{rechnung_id}/positionen",
    response_model=RechnungRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("abrechnung", "bearbeiten")),
    ],
)
async def add_position(
    rechnung_id: UUID,
    body: RechnungPositionCreate,
    session: AsyncSession = Depends(get_db),
) -> RechnungRead:
    rechnung = await session.get(Rechnung, rechnung_id)
    if rechnung is None or rechnung.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rechnung nicht gefunden")
    if rechnung.status != "entwurf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Positionen können nur im Entwurf ergänzt werden"
        )

    bestehende = await positionen_fuer(session, rechnung_id)
    naechste_position = max((p.position for p in bestehende), default=0) + 1
    session.add(
        RechnungPosition(
            mandant_id=rechnung.mandant_id,
            rechnung_id=rechnung_id,
            position=naechste_position,
            beschreibung=body.beschreibung,
            menge=body.menge,
            einheit=body.einheit,
            einzelpreis=body.einzelpreis,
        )
    )
    await session.flush()
    await session.refresh(rechnung)
    return await to_read_model(session, rechnung)


@router.get("/{rechnung_id}/positionsvorschlaege", response_model=list[RechnungPositionVorschlag])
async def get_positionsvorschlaege(
    rechnung_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> list[RechnungPositionVorschlag]:
    rechnung = await session.get(Rechnung, rechnung_id)
    if rechnung is None or rechnung.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rechnung nicht gefunden")
    if rechnung.vorgang_id is None:
        return []
    return await positionen_vorschlaege_fuer_vorgang(session, rechnung.vorgang_id)


async def _auf_bezahlt_setzen(
    session: AsyncSession, rechnung: Rechnung, auth: AuthContext, *, bezahlt_am: datetime
) -> None:
    """Einzige Stelle, die eine Rechnung auf 'bezahlt' abschliesst und dabei
    den Vorgang auf 'abgerechnet' setzt -- aufgerufen sowohl vom manuellen
    PATCH-Abschluss als auch vom Zahlungs-Endpunkt, damit der Nebeneffekt in
    beiden Faellen identisch ist und NIE bei teilweise_bezahlt feuert."""
    rechnung.status = "bezahlt"
    rechnung.bezahlt_am = bezahlt_am
    if rechnung.vorgang_id is not None:
        vorgang = await session.get(Vorgang, rechnung.vorgang_id)
        if vorgang is not None and vorgang.status != "abgerechnet":
            vorgang.status = "abgerechnet"


@router.patch(
    "/{rechnung_id}",
    response_model=RechnungRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("abrechnung", "bearbeiten")),
    ],
)
async def update_rechnung(
    rechnung_id: UUID,
    body: RechnungUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RechnungRead:
    rechnung = await session.get(Rechnung, rechnung_id)
    if rechnung is None or rechnung.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rechnung nicht gefunden")

    if body.betrag_netto is not None:
        if rechnung.status != "entwurf":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Betrag kann nur im Entwurf geändert werden"
            )
        bestehende_positionen = await positionen_fuer(session, rechnung_id)
        if bestehende_positionen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Diese Rechnung hat eigene Positionen -- der Betrag ergibt sich aus deren Summe",
            )
        rechnung.betrag_netto = body.betrag_netto
    if body.faellig_am is not None or body.leistungsdatum is not None:
        # GoBD: beide Felder stehen im archivierten PDF, leistungsdatum ist
        # zudem Pflichtangabe nach Paragraph 14 Abs. 4 Nr. 6 UStG -- nach dem
        # Versand duerfen sie sich nicht mehr aendern.
        if rechnung.status != "entwurf":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Fälligkeit und Leistungsdatum können nur im Entwurf geändert werden",
            )
        if body.faellig_am is not None:
            rechnung.faellig_am = body.faellig_am
        if body.leistungsdatum is not None:
            rechnung.leistungsdatum = body.leistungsdatum

    neuer_status = body.status
    if neuer_status is not None:
        if neuer_status not in _GUELTIGE_UEBERGAENGE.get(rechnung.status, set()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Statuswechsel von '{rechnung.status}' nach '{neuer_status}' nicht erlaubt",
            )
        jetzt = datetime.now(timezone.utc)
        if neuer_status == "versendet":
            rechnung.versendet_am = jetzt
            rechnung.status = neuer_status
            kunde = await session.get(Kunde, rechnung.kunde_id)
            mandant = await session.get(Mandant, auth.mandant_id)
            await archiviere_pdf(session, rechnung, mandant, kunde)
        elif neuer_status == "bezahlt":
            # Invariante offener_betrag == brutto - Summe(Zahlungen) muss
            # immer gelten -- ein manueller "als bezahlt markieren"-Abschluss
            # ohne Gegenbuchung wuerde sie brechen (das genaue Altdaten-
            # problem, das der Backfill in Migration 0056 behoben hat).
            positionen = await positionen_fuer(session, rechnung_id)
            zahlungen = await zahlungen_fuer(session, rechnung_id)
            offen = brutto_betrag(rechnung, positionen) - bezahlter_betrag(zahlungen)
            if offen > 0:
                session.add(
                    RechnungZahlung(
                        mandant_id=rechnung.mandant_id,
                        rechnung_id=rechnung.id,
                        betrag=offen,
                        datum=date.today(),
                        erstellt_von=auth.user_id,
                        notiz="Restbetrag beim manuellen Abschluss gebucht",
                    )
                )
            await _auf_bezahlt_setzen(session, rechnung, auth, bezahlt_am=jetzt)

        if rechnung.vorgang_id is not None:
            vorgang = await session.get(Vorgang, rechnung.vorgang_id)
            if vorgang is not None:
                session.add(
                    VorgangEvent(
                        mandant_id=auth.mandant_id,
                        vorgang_id=vorgang.id,
                        event_type="rechnung_status",
                        author_user_id=auth.user_id,
                        body=f"Rechnung {rechnung.rechnungsnummer}: Status '{neuer_status}'",
                        payload={"rechnung_id": str(rechnung.id), "status": neuer_status},
                    )
                )

    await session.flush()
    await session.refresh(rechnung)
    return await to_read_model(session, rechnung)


@router.post(
    "/{rechnung_id}/storno",
    response_model=RechnungRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("abrechnung", "bearbeiten")),
    ],
)
async def storno_rechnung(
    rechnung_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RechnungRead:
    rechnung = await session.get(Rechnung, rechnung_id)
    if rechnung is None or rechnung.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rechnung nicht gefunden")
    if rechnung.status not in ("versendet", "teilweise_bezahlt", "bezahlt"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nur versendete, teilweise bezahlte oder bezahlte Rechnungen können storniert werden",
        )

    storno = await erstelle_stornorechnung(session, rechnung, auth.user_id)

    kunde = await session.get(Kunde, storno.kunde_id)
    mandant = await session.get(Mandant, auth.mandant_id)
    await archiviere_pdf(session, storno, mandant, kunde, storniert_rechnung=rechnung)

    if rechnung.vorgang_id is not None:
        vorgang = await session.get(Vorgang, rechnung.vorgang_id)
        if vorgang is not None:
            session.add(
                VorgangEvent(
                    mandant_id=auth.mandant_id,
                    vorgang_id=vorgang.id,
                    event_type="rechnung_status",
                    author_user_id=auth.user_id,
                    body=f"Rechnung {rechnung.rechnungsnummer} storniert durch {storno.rechnungsnummer}",
                    payload={"rechnung_id": str(rechnung.id), "storno_rechnung_id": str(storno.id)},
                )
            )
    await session.flush()
    await session.refresh(storno)
    return await to_read_model(session, storno)


@router.post(
    "/{rechnung_id}/zahlungen",
    response_model=RechnungRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("abrechnung", "bearbeiten")),
    ],
)
async def add_zahlung(
    rechnung_id: UUID,
    body: RechnungZahlungCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RechnungRead:
    rechnung = await session.get(Rechnung, rechnung_id)
    if rechnung is None or rechnung.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rechnung nicht gefunden")
    if rechnung.status not in ("versendet", "teilweise_bezahlt"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zahlungen sind erst ab dem Versand möglich",
        )
    if body.betrag <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Zahlungsbetrag muss positiv sein")
    zahlungsdatum = body.datum or date.today()
    if zahlungsdatum > date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Zahlungsdatum darf nicht in der Zukunft liegen"
        )
    if body.zahlungsart is not None and body.zahlungsart not in RECHNUNG_ZAHLUNGSARTEN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unbekannte Zahlungsart")

    positionen = await positionen_fuer(session, rechnung_id)
    zahlungen = await zahlungen_fuer(session, rechnung_id)
    brutto = brutto_betrag(rechnung, positionen)
    offener_betrag = brutto - bezahlter_betrag(zahlungen)
    if body.betrag > offener_betrag:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Zahlung übersteigt den offenen Betrag ({offener_betrag} EUR)",
        )

    session.add(
        RechnungZahlung(
            mandant_id=rechnung.mandant_id,
            rechnung_id=rechnung_id,
            betrag=body.betrag,
            datum=zahlungsdatum,
            zahlungsart=body.zahlungsart,
            notiz=body.notiz,
            erstellt_von=auth.user_id,
        )
    )
    await session.flush()

    neuer_offener_betrag = offener_betrag - body.betrag
    neuer_status = status_nach_zahlung(brutto, bezahlter_betrag(zahlungen) + body.betrag, rechnung.status)
    if neuer_status == "bezahlt":
        # bezahlt_am wird das Datum der Zahlung, die die Rechnung schliesst
        # -- nicht mehr immer "jetzt" wie vor Phase 2, das war der Kern des
        # fehlenden rueckdatierbaren Zahlungsdatums.
        await _auf_bezahlt_setzen(
            session, rechnung, auth, bezahlt_am=datetime.combine(zahlungsdatum, datetime.min.time(), timezone.utc)
        )
    else:
        rechnung.status = neuer_status

    if rechnung.vorgang_id is not None:
        vorgang = await session.get(Vorgang, rechnung.vorgang_id)
        if vorgang is not None:
            session.add(
                VorgangEvent(
                    mandant_id=auth.mandant_id,
                    vorgang_id=vorgang.id,
                    event_type="rechnung_status",
                    author_user_id=auth.user_id,
                    body=(
                        f"Rechnung {rechnung.rechnungsnummer}: Zahlung über {body.betrag} EUR erfasst "
                        f"({neuer_offener_betrag} EUR offen)"
                    ),
                    payload={"rechnung_id": str(rechnung.id), "betrag": str(body.betrag)},
                )
            )

    await session.flush()
    await session.refresh(rechnung)
    return await to_read_model(session, rechnung)


@router.post(
    "/{rechnung_id}/zahlungen/{zahlung_id}/storno",
    response_model=RechnungRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("abrechnung", "bearbeiten")),
    ],
)
async def storno_zahlung(
    rechnung_id: UUID,
    zahlung_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RechnungRead:
    """Korrigiert eine Fehlbuchung durch eine negative Gegenbuchung statt
    die Zeile zu aendern/loeschen -- das Zahlungs-Ledger bleibt additiv
    (siehe RechnungZahlung-Docstring). Umgeht bewusst _GUELTIGE_UEBERGAENGE:
    dieser Pfad korrigiert Bewegungsdaten, schreibt keinen Belegstatus fort."""
    rechnung = await session.get(Rechnung, rechnung_id)
    if rechnung is None or rechnung.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rechnung nicht gefunden")
    if rechnung.status == "storniert":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Rechnung ist storniert"
        )

    original = await session.get(RechnungZahlung, zahlung_id)
    if original is None or original.rechnung_id != rechnung_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zahlung nicht gefunden")
    if original.betrag <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Nur Zahlungen können storniert werden"
        )

    bereits_stornierte = await session.execute(
        select(RechnungZahlung).where(RechnungZahlung.storniert_zahlung_id == zahlung_id)
    )
    if bereits_stornierte.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Diese Zahlung wurde bereits storniert"
        )

    session.add(
        RechnungZahlung(
            mandant_id=rechnung.mandant_id,
            rechnung_id=rechnung_id,
            betrag=-original.betrag,
            datum=date.today(),
            erstellt_von=auth.user_id,
            notiz=f"Storno der Zahlung vom {original.datum.strftime('%d.%m.%Y')}",
            storniert_zahlung_id=zahlung_id,
        )
    )
    await session.flush()

    positionen = await positionen_fuer(session, rechnung_id)
    zahlungen = await zahlungen_fuer(session, rechnung_id)
    brutto = brutto_betrag(rechnung, positionen)
    bezahlt = bezahlter_betrag(zahlungen)
    if bezahlt <= 0:
        rechnung.status = "versendet"
        rechnung.bezahlt_am = None
    elif bezahlt < brutto:
        rechnung.status = "teilweise_bezahlt"
        rechnung.bezahlt_am = None
    # bezahlt >= brutto bliebe "bezahlt" -- praktisch nur bei einem Storno,
    # das den offenen Betrag nicht wirklich veraendert.

    if rechnung.vorgang_id is not None:
        vorgang = await session.get(Vorgang, rechnung.vorgang_id)
        if vorgang is not None:
            session.add(
                VorgangEvent(
                    mandant_id=auth.mandant_id,
                    vorgang_id=vorgang.id,
                    event_type="rechnung_status",
                    author_user_id=auth.user_id,
                    body=f"Rechnung {rechnung.rechnungsnummer}: Zahlung über {original.betrag} EUR storniert",
                    payload={"rechnung_id": str(rechnung.id), "zahlung_id": str(zahlung_id)},
                )
            )

    await session.flush()
    await session.refresh(rechnung)
    return await to_read_model(session, rechnung)


@router.get("/{rechnung_id}/pdf")
async def rechnung_pdf(
    rechnung_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    rechnung = await session.get(Rechnung, rechnung_id)
    if rechnung is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rechnung nicht gefunden")
    kunde = await session.get(Kunde, rechnung.kunde_id)
    mandant = await session.get(Mandant, auth.mandant_id)
    storniert_rechnung = await _storniert_rechnung_fuer(session, rechnung)

    pdf_bytes = await pdf_bytes_fuer(session, rechnung, mandant, kunde, storniert_rechnung=storniert_rechnung)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{rechnung.rechnungsnummer}.pdf"'},
    )


@router.get("/{rechnung_id}/xml")
async def rechnung_xml(
    rechnung_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    rechnung = await session.get(Rechnung, rechnung_id)
    if rechnung is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rechnung nicht gefunden")
    if not rechnung.xml_object_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Keine ZUGFeRD-XML fuer diese Rechnung vorhanden")
    xml_bytes = await storage_service.download_bytes(rechnung.xml_object_key)
    return Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": 'inline; filename="factur-x.xml"'},
    )


@router.get("/{rechnung_id}/emails", response_model=list[EmailLogRead])
async def list_rechnung_emails(
    rechnung_id: UUID, session: AsyncSession = Depends(get_db)
) -> list[EmailLog]:
    rechnung = await session.get(Rechnung, rechnung_id)
    if rechnung is None or rechnung.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rechnung nicht gefunden")
    result = await session.execute(
        select(EmailLog)
        .where(EmailLog.entity_type == "rechnung", EmailLog.entity_id == rechnung_id)
        .order_by(EmailLog.created_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/{rechnung_id}/email",
    response_model=EmailLogRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("abrechnung", "bearbeiten")),
    ],
)
async def send_rechnung_email(
    rechnung_id: UUID,
    body: EmailMitAnhangSenden,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> EmailLog:
    rechnung = await session.get(Rechnung, rechnung_id)
    if rechnung is None or rechnung.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rechnung nicht gefunden")
    kunde = await session.get(Kunde, rechnung.kunde_id)
    mandant = await session.get(Mandant, auth.mandant_id)
    storniert_rechnung = await _storniert_rechnung_fuer(session, rechnung)
    pdf_bytes = await pdf_bytes_fuer(session, rechnung, mandant, kunde, storniert_rechnung=storniert_rechnung)
    dateiname = f"{rechnung.rechnungsnummer}.pdf"

    log = await send_email_and_log(
        session,
        auth.mandant_id,
        entity_type="rechnung",
        entity_id=rechnung_id,
        to=body.empfaenger,
        subject=body.betreff or f"Rechnung {rechnung.rechnungsnummer}",
        body=body.inhalt or f"Anbei erhalten Sie unsere Rechnung {rechnung.rechnungsnummer}.",
        gesendet_von=auth.user_id,
        attachment=(dateiname, pdf_bytes, "application/pdf"),
    )
    return log
