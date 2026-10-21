from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal
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
from app.models.angebot import Angebot
from app.models.email_log import EmailLog
from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.material import Material, MaterialVerwendung
from app.models.rechnung import RECHNUNG_ZAHLUNGSARTEN, Rechnung, RechnungPosition, RechnungZahlung
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.email import EmailLogRead, EmailMitAnhangSenden
from app.models.zeiterfassung import Zeiterfassung
from app.schemas.rechnung import (
    AbrechenbarerVorgang,
    AbschlaegeAnrechnen,
    GutschriftCreate,
    RechnungAusAngebotCreate,
    RechnungCreate,
    RechnungListe,
    RechnungPositionCreate,
    RechnungPositionUpdate,
    RechnungPositionVorschlag,
    RechnungRead,
    RechnungUpdate,
    RechnungVorgangUebernahme,
    RechnungZahlungCreate,
)
from app.services import papierkorb_service, rechnungsart_service, steuer_service, storage_service
from app.services.audit_service import log_action
from app.services.audit_service import export_protokollieren
from app.services.csv_service import csv_response
from app.services.email_service import send_email_and_log
from app.services.numbering_service import next_rechnungsnummer
from app.services.rechnung_service import (
    archiviere_pdf,
    bezahlter_betrag,
    brutto_betrag,
    brutto_sql,
    erstelle_stornorechnung,
    offener_betrag_regel,
    kunden_namen_fuer,
    material_abrechnen,
    material_abrechnung_zuruecksetzen,
    material_freigeben_fuer_rechnung,
    netto_sql,
    offen_sql,
    pdf_bytes_fuer,
    positionen_fuer,
    positionen_vorschlaege_fuer_vorgang,
    pruefe_versand,
    status_nach_zahlung,
    to_read_model,
    to_read_model_bulk,
    VersandFehler,
    versand_meldung,
    vorgang_uebernehmen,
    zahlungen_fuer,
    zeiterfassung_abrechnen,
    zeiterfassung_abrechnung_zuruecksetzen,
    zeiterfassung_freigeben_fuer_rechnung,
)
from app.services.zuweisung_service import (
    erlaubte_kunde_ids,
    require_kunde_zugewiesen,
    require_kunde_zugriff,
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


async def _rechnung_laden(
    session: AsyncSession,
    auth: AuthContext,
    rechnung_id: UUID,
    *,
    geloeschte_zulassen: bool = False,
) -> Rechnung:
    """Zentraler Zugriff auf eine Rechnung per ID: Papierkorb + Einschraenkung
    auf zugewiesene Kunden (nur_zugewiesene_kunden) -> 404."""
    rechnung = await session.get(Rechnung, rechnung_id)
    if rechnung is None or (rechnung.geloescht_am is not None and not geloeschte_zulassen):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rechnung nicht gefunden")
    await require_kunde_zugriff(session, auth, rechnung.kunde_id, "Rechnung nicht gefunden")
    return rechnung


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
    rechnungsart: str | None = None,
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
    if rechnungsart:
        bedingungen.append(Rechnung.rechnungsart == rechnungsart)
    if nur_offen and not nur_ueberfaellig:
        # Ein versendeter Beleg ist nur offen, solange etwas aussteht -- eine
        # durch Gutschrift verrechnete Rechnung nicht, die Gutschrift mit
        # Guthaben (negativer offener Betrag) schon.
        bedingungen.append(Rechnung.status.in_(_OFFENE_STATUS))
        bedingungen.append(or_(Rechnung.status == "entwurf", offen_sql() != 0))
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
    rechnungsart: Literal["rechnung", "abschlag", "schluss", "gutschrift"] | None = Query(default=None),
    sort: str = Query(default="-datum"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    auth: AuthContext = Depends(get_current_user),
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
        rechnungsart,
    )
    erlaubte_kunden = await erlaubte_kunde_ids(session, auth)
    if erlaubte_kunden is not None:
        bedingungen.append(Rechnung.kunde_id.in_(erlaubte_kunden))

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
    auth: AuthContext = Depends(get_current_user),
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
    erlaubte_kunden = await erlaubte_kunde_ids(session, auth)
    if erlaubte_kunden is not None:
        bedingungen.append(Rechnung.kunde_id.in_(erlaubte_kunden))
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
            # Gemischte Belege haben keinen einen Satz -- alle Saetze ausweisen.
            "/".join(str(g.satz) for g in r.steuergruppen) if len(r.steuergruppen) > 1 else str(r.mwst_satz),
            str(r.betrag_brutto),
            str(r.tage_ueberfaellig),
            str(r.mahnstufe),
        ]
        for r in gelesen
    ]
    await export_protokollieren(
        session, mandant_id=auth.mandant_id, actor_user_id=auth.user_id, art="csv", objekt="rechnungen", zeilen=len(rows)
    )
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


# Muss VOR "/{rechnung_id}" stehen (siehe export/csv).
@router.get(
    "/abrechenbare-vorgaenge",
    response_model=list[AbrechenbarerVorgang],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("abrechnung", "erstellen")),
    ],
)
async def list_abrechenbare_vorgaenge(
    kunde_id: UUID = Query(...),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[AbrechenbarerVorgang]:
    """Auswahlliste fuer "Vorgang hinzufuegen". Dieselben Kriterien wie die
    Vorschlaege (positionen_vorschlaege_fuer_vorgang) -- eine Query je Quelle
    gruppiert ueber alle Vorgaenge des Kunden statt eine je Vorgang. Ein
    Vorgang erscheint bei offenen Stunden ODER offenem Material."""
    await require_kunde_zugriff(session, auth, kunde_id, "Kunde nicht gefunden")
    dauer = func.extract("epoch", Zeiterfassung.ende_at - Zeiterfassung.start_at)
    ohne_svs = func.coalesce(func.sum(case((Zeiterfassung.lv_position_id.is_(None), dauer), else_=0)), 0)
    mit_svs = func.coalesce(func.sum(case((Zeiterfassung.lv_position_id.is_not(None), dauer), else_=0)), 0)
    zeit_result = await session.execute(
        select(Vorgang.id, Vorgang.vorgangsnummer, Vorgang.titel, ohne_svs, mit_svs)
        .join(Zeiterfassung, Zeiterfassung.vorgang_id == Vorgang.id)
        .where(
            Vorgang.kunde_id == kunde_id,
            Vorgang.geloescht_am.is_(None),
            Zeiterfassung.kategorie == "auftrag",
            Zeiterfassung.abrechenbar.is_(True),
            Zeiterfassung.ende_at.is_not(None),
            Zeiterfassung.buchungsstatus == "gebucht",
            Zeiterfassung.geloescht_am.is_(None),
        )
        .group_by(Vorgang.id, Vorgang.vorgangsnummer, Vorgang.titel)
        .having(ohne_svs + mit_svs > 0)
    )
    material_result = await session.execute(
        select(
            Vorgang.id,
            Vorgang.vorgangsnummer,
            Vorgang.titel,
            func.count(func.distinct(MaterialVerwendung.material_id)),
        )
        .join(MaterialVerwendung, MaterialVerwendung.vorgang_id == Vorgang.id)
        .where(
            Vorgang.kunde_id == kunde_id,
            Vorgang.geloescht_am.is_(None),
            MaterialVerwendung.abrechnungsstatus == "offen",
        )
        .group_by(Vorgang.id, Vorgang.vorgangsnummer, Vorgang.titel)
    )
    stunde = Decimal("3600")
    cent = Decimal("0.01")
    eintraege: dict[UUID, AbrechenbarerVorgang] = {}
    for vorgang_id, nummer, titel, o, m in zeit_result.all():
        eintraege[vorgang_id] = AbrechenbarerVorgang(
            vorgang_id=vorgang_id,
            vorgangsnummer=nummer,
            titel=titel,
            stunden_ohne_svs=(Decimal(str(o)) / stunde).quantize(cent),
            stunden_mit_svs=(Decimal(str(m)) / stunde).quantize(cent),
        )
    for vorgang_id, nummer, titel, anzahl in material_result.all():
        eintrag = eintraege.get(vorgang_id)
        if eintrag is None:
            eintrag = eintraege[vorgang_id] = AbrechenbarerVorgang(
                vorgang_id=vorgang_id,
                vorgangsnummer=nummer,
                titel=titel,
                stunden_ohne_svs=Decimal("0.00"),
                stunden_mit_svs=Decimal("0.00"),
            )
        eintrag.material_offen = anzahl
    return sorted(eintraege.values(), key=lambda e: e.vorgangsnummer, reverse=True)


@router.get("/{rechnung_id}", response_model=RechnungRead)
async def get_rechnung(
    rechnung_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RechnungRead:
    rechnung = await _rechnung_laden(session, auth, rechnung_id)
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
    rechnung = await _rechnung_laden(session, auth, rechnung_id)
    if rechnung.status != "entwurf":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nur Rechnungen im Entwurf können gelöscht werden",
        )
    await papierkorb_service.soft_delete(
        session, entity_typ="rechnung", entity_id=rechnung_id, actor_user_id=auth.user_id
    )
    await _audit(session, auth, "rechnung_entwurf_geloescht", rechnung)


def _steuer_fuer_position(
    body: RechnungPositionCreate, beleg_mwst_satz: Decimal, *, kleinunternehmer: bool
) -> steuer_service.PositionSteuer:
    try:
        return steuer_service.loese_steuer_auf(
            kategorie=body.steuer_kategorie,
            satz=body.steuer_satz,
            grund=body.steuer_grund,
            grund_text=body.steuer_grund_text,
            beleg_mwst_satz=beleg_mwst_satz,
            kleinunternehmer=kleinunternehmer,
        )
    except steuer_service.SteuerFehler as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


def _pruefe_13b_beim_anlegen(kunde: Kunde, rechnung_leistungsdatum: date | None) -> None:
    """Reverse Charge (AE) haengt am Kunden der Rechnung, nicht an der Position.
    Beim Versand wird erneut geprueft (rechnung_service.pruefe_versand)."""
    probleme = steuer_service.pruefe_13b_voraussetzungen(kunde, rechnung_leistungsdatum)
    if probleme:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Reverse Charge (§ 13b UStG) nicht möglich: " + "; ".join(probleme),
        )


def _neue_positionen(
    rechnung_id: UUID,
    mandant_id: UUID,
    eintraege: list[RechnungPositionCreate],
    beleg_mwst_satz: Decimal,
    *,
    kleinunternehmer: bool,
) -> list[RechnungPosition]:
    positionen = []
    for i, e in enumerate(eintraege):
        steuer = _steuer_fuer_position(e, beleg_mwst_satz, kleinunternehmer=kleinunternehmer)
        positionen.append(
            RechnungPosition(
                mandant_id=mandant_id,
                rechnung_id=rechnung_id,
                position=i + 1,
                beschreibung=e.beschreibung,
                menge=e.menge,
                einheit=e.einheit,
                einzelpreis=e.einzelpreis,
                steuer_kategorie=steuer.kategorie,
                steuer_satz=steuer.satz,
                steuer_grund=steuer.grund,
                steuer_grund_text=steuer.grund_text,
                quelle=e.quelle,
            )
        )
    return positionen


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
    kunde = await session.get(Kunde, body.kunde_id)
    if kunde is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kunde nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    await require_kunde_zugewiesen(session, auth, body.kunde_id)
    vorgang = None
    if body.vorgang_id is not None:
        vorgang = await session.get(Vorgang, body.vorgang_id)
        if vorgang is None or vorgang.geloescht_am is not None:
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
    ist_kleinunternehmer = steuer_service.ist_kleinunternehmer(mandant)
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
        rechnungsart=body.rechnungsart,
    )
    session.add(rechnung)
    await session.flush()

    neue_positionen = _neue_positionen(
        rechnung.id, auth.mandant_id, body.positionen, mwst_satz, kleinunternehmer=ist_kleinunternehmer
    )
    if any(p.steuer_kategorie == "AE" for p in neue_positionen):
        _pruefe_13b_beim_anlegen(kunde, body.leistungsdatum)
    for p in neue_positionen:
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
                body=f"{rechnungsart_service.rechnungsart_label(rechnung)} {rechnungsnummer} erstellt (Entwurf)",
                payload={"rechnung_id": str(rechnung.id), "status": "entwurf"},
            )
        )
    await _audit(session, auth, "rechnung_erstellt", rechnung)
    await session.flush()
    return await to_read_model(session, rechnung)


_ERSTELLEN = [
    Depends(require_roles("mandant_admin", "custom")),
    Depends(require_recht("abrechnung", "erstellen")),
]


@router.post("/aus-angebot", response_model=RechnungRead, status_code=status.HTTP_201_CREATED, dependencies=_ERSTELLEN)
async def create_rechnung_aus_angebot(
    body: RechnungAusAngebotCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RechnungRead:
    """Rechnung, Abschlag oder Schlussrechnung (mit Anrechnung der Abschlaege)
    zu einem angenommenen Angebot -- immer als Entwurf."""
    angebot = await session.get(Angebot, body.angebot_id)
    if angebot is None or angebot.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Angebot nicht gefunden")
    await require_kunde_zugriff(session, auth, angebot.kunde_id, "Angebot nicht gefunden")
    await require_kunde_zugewiesen(session, auth, angebot.kunde_id)
    mandant = await session.get(Mandant, auth.mandant_id)
    rechnung = await rechnungsart_service.rechnung_aus_angebot(
        session, body, mandant=mandant, actor_user_id=auth.user_id
    )
    await _audit(session, auth, "rechnung_erstellt", rechnung, angebot_id=str(angebot.id))
    return await to_read_model(session, rechnung)


@router.post("/{rechnung_id}/abschlaege-anrechnen", response_model=RechnungRead, dependencies=_ERSTELLEN)
async def abschlaege_anrechnen(
    rechnung_id: UUID,
    body: AbschlaegeAnrechnen | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RechnungRead:
    """Macht einen Entwurf zur Schlussrechnung: rechnet die Abschlagsrechnungen
    desselben Kunden an, die zum selben Angebot oder Vorgang gehoeren."""
    rechnung = await _rechnung_laden(session, auth, rechnung_id)
    if rechnung.status != "entwurf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Abschläge können nur im Entwurf angerechnet werden"
        )
    if rechnung.rechnungsart not in ("rechnung", "schluss"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Abschläge können nur in einer Rechnung oder Schlussrechnung angerechnet werden",
        )
    await rechnungsart_service.abschlaege_anrechnen(session, rechnung, body or AbschlaegeAnrechnen())
    await session.refresh(rechnung)
    await _audit(session, auth, "abschlaege_angerechnet", rechnung)
    return await to_read_model(session, rechnung)


@router.post(
    "/{rechnung_id}/gutschrift", response_model=RechnungRead, status_code=status.HTTP_201_CREATED, dependencies=_ERSTELLEN
)
async def create_gutschrift(
    rechnung_id: UUID,
    body: GutschriftCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RechnungRead:
    """Voll- oder Teil-Gutschrift zu einer versendeten Rechnung. Das Original
    bleibt gueltig; die Gutschrift ist sofort versendet (wie ein Storno-Beleg)
    und senkt dessen offenen Betrag."""
    original = await _rechnung_laden(session, auth, rechnung_id)
    mandant = await session.get(Mandant, auth.mandant_id)
    gutschrift = await rechnungsart_service.erstelle_gutschrift(
        session, original, body, mandant=mandant, actor_user_id=auth.user_id
    )
    kunde = await session.get(Kunde, gutschrift.kunde_id)
    await archiviere_pdf(session, gutschrift, mandant, kunde, strikt=False)

    vorher = original.status
    voll_gutgeschrieben = await rechnungsart_service.status_nach_gutschriften(session, original)
    if vorher != "bezahlt" and original.status == "bezahlt" and not voll_gutgeschrieben:
        # Der Rest ist bezahlt -- wie beim Zahlungs-Abschluss gilt der Vorgang
        # als abgerechnet. Eine vollstaendig gutgeschriebene Rechnung hat
        # nichts abgerechnet.
        await _auf_bezahlt_setzen(session, original, auth, bezahlt_am=original.bezahlt_am)
    await rechnungsart_service.vorgang_event_gutschrift(session, original, gutschrift, auth.user_id)
    await session.flush()
    await session.refresh(gutschrift)
    await _audit(session, auth, "gutschrift_erstellt", gutschrift, bezug_rechnung_id=str(original.id))
    return await to_read_model(session, gutschrift)


async def _entwurf_laden(session: AsyncSession, auth: AuthContext, rechnung_id: UUID) -> Rechnung:
    rechnung = await _rechnung_laden(session, auth, rechnung_id)
    if rechnung.status != "entwurf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Vorgänge können nur im Entwurf hinzugefügt werden"
        )
    return rechnung


async def _vorgang_des_kunden(session: AsyncSession, vorgang_id: UUID, kunde_id: UUID) -> Vorgang:
    vorgang = await session.get(Vorgang, vorgang_id)
    if vorgang is None or vorgang.geloescht_am is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    if vorgang.kunde_id != kunde_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Vorgang gehört nicht zum Kunden der Rechnung"
        )
    return vorgang


@router.get(
    "/{rechnung_id}/vorgaenge/{vorgang_id}/vorschlaege",
    response_model=list[RechnungPositionVorschlag],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("abrechnung", "bearbeiten")),
    ],
)
async def get_vorgang_vorschlaege(
    rechnung_id: UUID,
    vorgang_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[RechnungPositionVorschlag]:
    rechnung = await _entwurf_laden(session, auth, rechnung_id)
    vorgang = await _vorgang_des_kunden(session, vorgang_id, rechnung.kunde_id)
    mandant = await session.get(Mandant, auth.mandant_id)
    return await positionen_vorschlaege_fuer_vorgang(session, vorgang.id, mandant)


@router.post(
    "/{rechnung_id}/vorgaenge",
    response_model=RechnungRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("abrechnung", "bearbeiten")),
    ],
)
async def add_vorgang(
    rechnung_id: UUID,
    body: RechnungVorgangUebernahme,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RechnungRead:
    rechnung = await _entwurf_laden(session, auth, rechnung_id)
    if not body.auswahl:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Keine Posten ausgewählt")
    vorgang = await _vorgang_des_kunden(session, body.vorgang_id, rechnung.kunde_id)
    mandant = await session.get(Mandant, auth.mandant_id)
    await vorgang_uebernehmen(
        session,
        rechnung=rechnung,
        vorgang=vorgang,
        mandant=mandant,
        stundensatz=body.stundensatz,
        auswahl=body.auswahl,
        actor_user_id=auth.user_id,
    )
    await session.refresh(rechnung)
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
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RechnungRead:
    rechnung = await _rechnung_laden(session, auth, rechnung_id)
    if rechnung.status != "entwurf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Positionen können nur im Entwurf ergänzt werden"
        )

    # Nur eine Material-Position mit Materialbezug sperrt Verwendungen; ohne
    # material_id oder Vorgang bleibt "material" eine freie Position.
    material_gesperrt = (
        body.quelle == "material" and body.material_id is not None and rechnung.vorgang_id is not None
    )
    if material_gesperrt and await session.get(Material, body.material_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Material nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )

    mandant = await session.get(Mandant, auth.mandant_id)
    steuer = _steuer_fuer_position(
        body, rechnung.mwst_satz, kleinunternehmer=steuer_service.ist_kleinunternehmer(mandant)
    )
    if steuer.kategorie == "AE":
        _pruefe_13b_beim_anlegen(await session.get(Kunde, rechnung.kunde_id), rechnung.leistungsdatum)
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
            steuer_kategorie=steuer.kategorie,
            steuer_satz=steuer.satz,
            steuer_grund=steuer.grund,
            steuer_grund_text=steuer.grund_text,
            quelle=body.quelle,
            vorgang_id=(
                rechnung.vorgang_id
                if body.quelle in ("zeit", "fahrzeit", "fahrtkosten", "leistung") or material_gesperrt
                else None
            ),
            lv_position_id=body.lv_position_id if body.quelle == "leistung" else None,
            material_id=body.material_id if material_gesperrt else None,
        )
    )
    if material_gesperrt:
        await material_abrechnen(
            session, vorgang_id=rechnung.vorgang_id, material_id=body.material_id, rechnung_id=rechnung.id
        )
    # Stufe 4 (docs/konzepte/ZEITERFASSUNG.md Abschnitt 8): eine aus einem
    # Zeit-Vorschlag uebernommene Position sperrt die zugrunde liegenden
    # Zeiterfassung-Eintraege (buchungsstatus -> 'abgerechnet'). Bei "leistung"
    # nur die SVS-gekoppelte Zeit; LV-Verwendungen bleiben bewusst aussen vor
    # (siehe zeiterfassung_abrechnen), Material sperrt oben.
    if body.quelle in ("zeit", "fahrzeit", "fahrtkosten", "leistung") and rechnung.vorgang_id is not None:
        await zeiterfassung_abrechnen(
            session,
            vorgang_id=rechnung.vorgang_id,
            quelle=body.quelle,
            rechnung_id=rechnung.id,
            geaendert_von=auth.user_id,
            lv_position_id=body.lv_position_id if body.quelle == "leistung" else None,
        )
    await session.flush()
    await session.refresh(rechnung)
    return await to_read_model(session, rechnung)


@router.delete(
    "/{rechnung_id}/positionen/{position_id}",
    response_model=RechnungRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("abrechnung", "bearbeiten")),
    ],
)
async def remove_position(
    rechnung_id: UUID,
    position_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RechnungRead:
    rechnung = await _rechnung_laden(session, auth, rechnung_id)
    if rechnung.status != "entwurf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Positionen können nur im Entwurf entfernt werden"
        )
    position = await session.get(RechnungPosition, position_id)
    if position is None or position.rechnung_id != rechnung_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position nicht gefunden")

    # Stunden- und km-Anteil einer Zeile sind getrennt gesperrt (Migration
    # 0097), eine Position gibt daher nur ihren eigenen Anteil frei. Geschwister
    # sind nur noch Positionen derselben Quelle (und bei "leistung" derselben
    # LV-Position) auf derselben Rechnung und demselben Vorgang -- sie sperren
    # dieselben Zeilen, also erst bei der letzten freigeben.
    # Der Vorgang haengt an der Position (Sammelrechnung); rechnung.vorgang_id
    # ist nur der Fallback fuer Positionen aus der Zeit vor Migration 0087.
    entsperr_vorgang_id = position.vorgang_id or rechnung.vorgang_id
    if (
        position.quelle in ("zeit", "fahrzeit", "fahrtkosten", "leistung")
        and entsperr_vorgang_id is not None
    ):
        rest = await positionen_fuer(session, rechnung_id)
        geschwister_besteht = any(
            p.id != position.id
            and p.quelle == position.quelle
            and (p.vorgang_id or rechnung.vorgang_id) == entsperr_vorgang_id
            and (position.quelle != "leistung" or p.lv_position_id == position.lv_position_id)
            for p in rest
        )
        if not geschwister_besteht:
            await zeiterfassung_abrechnung_zuruecksetzen(
                session,
                rechnung_id=rechnung_id,
                quelle=position.quelle,
                vorgang_id=entsperr_vorgang_id,
                geaendert_von=auth.user_id,
                lv_position_id=position.lv_position_id,
            )

    if position.quelle == "material" and position.material_id is not None and entsperr_vorgang_id is not None:
        rest = await positionen_fuer(session, rechnung_id)
        geschwister_besteht = any(
            p.id != position.id
            and p.quelle == "material"
            and p.material_id == position.material_id
            and (p.vorgang_id or rechnung.vorgang_id) == entsperr_vorgang_id
            for p in rest
        )
        if not geschwister_besteht:
            await material_abrechnung_zuruecksetzen(
                session,
                rechnung_id=rechnung_id,
                vorgang_id=entsperr_vorgang_id,
                material_id=position.material_id,
            )

    await session.delete(position)
    await session.flush()
    await session.refresh(rechnung)
    return await to_read_model(session, rechnung)


@router.patch(
    "/{rechnung_id}/positionen/{position_id}",
    response_model=RechnungRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("abrechnung", "bearbeiten")),
    ],
)
async def update_position(
    rechnung_id: UUID,
    position_id: UUID,
    body: RechnungPositionUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> RechnungRead:
    rechnung = await _rechnung_laden(session, auth, rechnung_id)
    if rechnung.status != "entwurf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Positionen können nur im Entwurf geändert werden"
        )
    position = await session.get(RechnungPosition, position_id)
    if position is None or position.rechnung_id != rechnung_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position nicht gefunden")
    if position.abschlag_rechnung_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Abzugspositionen einer Schlussrechnung sind nicht änderbar – bitte entfernen "
            "(hebt die Anrechnung auf) und den Abschlag erneut anrechnen",
        )

    if body.beschreibung is not None:
        position.beschreibung = body.beschreibung
    if body.einzelpreis is not None:
        position.einzelpreis = body.einzelpreis
    if any(
        wert is not None
        for wert in (body.steuer_kategorie, body.steuer_satz, body.steuer_grund, body.steuer_grund_text)
    ):
        mandant = await session.get(Mandant, auth.mandant_id)
        try:
            steuer = steuer_service.aendere_steuer(
                aktuell_kategorie=position.steuer_kategorie,
                aktuell_satz=position.steuer_satz,
                aktuell_grund=position.steuer_grund,
                aktuell_grund_text=position.steuer_grund_text,
                kategorie=body.steuer_kategorie,
                satz=body.steuer_satz,
                grund=body.steuer_grund,
                grund_text=body.steuer_grund_text,
                kleinunternehmer=steuer_service.ist_kleinunternehmer(mandant),
            )
        except steuer_service.SteuerFehler as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        if steuer.kategorie == "AE":
            _pruefe_13b_beim_anlegen(await session.get(Kunde, rechnung.kunde_id), rechnung.leistungsdatum)
        position.steuer_kategorie, position.steuer_satz = steuer.kategorie, steuer.satz
        position.steuer_grund, position.steuer_grund_text = steuer.grund, steuer.grund_text
    await session.flush()
    await session.refresh(position)
    await session.refresh(rechnung)
    return await to_read_model(session, rechnung)


@router.get("/{rechnung_id}/positionsvorschlaege", response_model=list[RechnungPositionVorschlag])
async def get_positionsvorschlaege(
    rechnung_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[RechnungPositionVorschlag]:
    rechnung = await _rechnung_laden(session, auth, rechnung_id)
    if rechnung.vorgang_id is None:
        return []
    mandant = await session.get(Mandant, auth.mandant_id)
    return await positionen_vorschlaege_fuer_vorgang(session, rechnung.vorgang_id, mandant)


async def _audit(
    session: AsyncSession, auth: AuthContext, aktion: str, rechnung: Rechnung, **payload
) -> None:
    """Beleg-Ereignis im Mandanten-Protokoll. Nur Referenzen und Belegdaten, keine
    Kundenstammdaten (die stehen im Beleg selbst)."""
    await log_action(
        session,
        aktion=aktion,
        mandant_id=rechnung.mandant_id,
        actor_user_id=auth.user_id,
        entity_type="rechnung",
        entity_id=rechnung.id,
        payload={"rechnungsnummer": rechnung.rechnungsnummer, "rechnungsart": rechnung.rechnungsart, **payload},
    )


async def _auf_bezahlt_setzen(
    session: AsyncSession, rechnung: Rechnung, auth: AuthContext, *, bezahlt_am: datetime
) -> None:
    """Einzige Stelle, die eine Rechnung auf 'bezahlt' abschliesst und dabei
    den Vorgang auf 'abgerechnet' setzt -- aufgerufen sowohl vom manuellen
    PATCH-Abschluss als auch vom Zahlungs-Endpunkt, damit der Nebeneffekt in
    beiden Faellen identisch ist und NIE bei teilweise_bezahlt feuert."""
    rechnung.status = "bezahlt"
    rechnung.bezahlt_am = bezahlt_am
    # Ein bezahlter Abschlag schliesst den Vorgang nicht ab -- die Leistung
    # ist erst mit der Schlussrechnung abgerechnet.
    if rechnung.vorgang_id is not None and rechnung.rechnungsart != "abschlag":
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
    rechnung = await _rechnung_laden(session, auth, rechnung_id)

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
            kunde = await session.get(Kunde, rechnung.kunde_id)
            mandant = await session.get(Mandant, auth.mandant_id)
            # Vor jeder Aenderung: bei fehlenden Pflichtangaben bleibt der Entwurf unberuehrt.
            probleme = pruefe_versand(mandant, rechnung, kunde, await positionen_fuer(session, rechnung_id))
            probleme += await rechnungsart_service.pruefe_abzuege_fuer_versand(session, rechnung)
            if probleme:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=versand_meldung(probleme)
                )
            rechnung.versendet_am = jetzt
            rechnung.status = neuer_status
            try:
                await archiviere_pdf(session, rechnung, mandant, kunde)
            except VersandFehler as exc:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
            await _audit(session, auth, "rechnung_versendet", rechnung)
        elif neuer_status == "bezahlt":
            if rechnung.rechnungsart == "gutschrift":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Gutschriften können nicht als bezahlt markiert werden"
                )
            # Invariante offener_betrag == brutto - Summe(Zahlungen) - Gutschriften
            # muss immer gelten -- ein manueller "als bezahlt markieren"-Abschluss
            # ohne Gegenbuchung wuerde sie brechen (das genaue Altdaten-
            # problem, das der Backfill in Migration 0056 behoben hat).
            positionen = await positionen_fuer(session, rechnung_id)
            zahlungen = await zahlungen_fuer(session, rechnung_id)
            offen = offener_betrag_regel(
                brutto_betrag(rechnung, positionen),
                bezahlter_betrag(zahlungen),
                await rechnungsart_service.gutschrift_summe(session, rechnung_id),
            )
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
            await _audit(session, auth, "rechnung_als_bezahlt_markiert", rechnung, restbetrag=str(offen))
        elif neuer_status == "storniert":
            await _audit(session, auth, "rechnung_entwurf_storniert", rechnung)

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
    rechnung = await _rechnung_laden(session, auth, rechnung_id)
    if rechnung.status not in ("versendet", "teilweise_bezahlt", "bezahlt"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nur versendete, teilweise bezahlte oder bezahlte Rechnungen können storniert werden",
        )

    if rechnung.rechnungsart == "abschlag":
        schluss = (await rechnungsart_service.abschlag_angerechnet_in(session, [rechnung.id])).get(rechnung.id)
        if schluss is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Der Abschlag ist in Schlussrechnung {schluss.rechnungsnummer} angerechnet und kann "
                "nicht storniert werden – bitte zuerst die Schlussrechnung stornieren",
            )
    gutschriften = await rechnungsart_service.gutschriften_zu(session, rechnung.id)
    if gutschriften:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Zu dieser Rechnung existieren Gutschriften ("
            + ", ".join(g.rechnungsnummer for g in gutschriften)
            + ") – ein Komplett-Storno ist nicht mehr möglich",
        )

    original_positionen = await positionen_fuer(session, rechnung.id)
    storno = await erstelle_stornorechnung(session, rechnung, auth.user_id)
    # Storno ist endgueltig: die Stunden gehen ohne Verweis zurueck in den Pool.
    await zeiterfassung_freigeben_fuer_rechnung(
        session, rechnung_id=rechnung.id, geaendert_von=auth.user_id, verweis_behalten=False
    )
    await material_freigeben_fuer_rechnung(session, rechnung_id=rechnung.id, verweis_behalten=False)

    kunde = await session.get(Kunde, storno.kunde_id)
    mandant = await session.get(Mandant, auth.mandant_id)
    await archiviere_pdf(session, storno, mandant, kunde, storniert_rechnung=rechnung, strikt=False)
    if rechnung.rechnungsart == "gutschrift" and rechnung.bezug_rechnung_id is not None:
        # Die stornierte Gutschrift deckt das Original nicht mehr.
        bezug = await session.get(Rechnung, rechnung.bezug_rechnung_id)
        if bezug is not None:
            await rechnungsart_service.status_nach_gutschriften(session, bezug)

    # Sammelrechnungen haben kein rechnung.vorgang_id -- die Vorgaenge stecken
    # in den Positionen.
    vorgang_ids = list(
        dict.fromkeys(
            v for v in [rechnung.vorgang_id, *(p.vorgang_id for p in original_positionen)] if v is not None
        )
    )
    for vorgang_id in vorgang_ids:
        vorgang = await session.get(Vorgang, vorgang_id)
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
    await _audit(session, auth, "rechnung_storniert", rechnung, storno_rechnung_id=str(storno.id), storno_rechnungsnummer=storno.rechnungsnummer)
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
    rechnung = await _rechnung_laden(session, auth, rechnung_id)
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

    if rechnung.rechnungsart == "gutschrift":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Zu Gutschriften können keine Zahlungen gebucht werden"
        )
    positionen = await positionen_fuer(session, rechnung_id)
    zahlungen = await zahlungen_fuer(session, rechnung_id)
    brutto = brutto_betrag(rechnung, positionen)
    gutschriften = await rechnungsart_service.gutschrift_summe(session, rechnung_id)
    offener_betrag = offener_betrag_regel(brutto, bezahlter_betrag(zahlungen), gutschriften)
    if body.betrag > offener_betrag:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Zahlung übersteigt den offenen Betrag ({offener_betrag} EUR)",
        )

    zahlung = RechnungZahlung(
        mandant_id=rechnung.mandant_id,
        rechnung_id=rechnung_id,
        betrag=body.betrag,
        datum=zahlungsdatum,
        zahlungsart=body.zahlungsart,
        notiz=body.notiz,
        erstellt_von=auth.user_id,
    )
    session.add(zahlung)
    await session.flush()
    await _audit(
        session, auth, "zahlung_gebucht", rechnung,
        zahlung_id=str(zahlung.id), betrag=str(body.betrag), datum=zahlungsdatum.isoformat(), zahlungsart=body.zahlungsart,
    )

    neuer_offener_betrag = offener_betrag - body.betrag
    neuer_status = status_nach_zahlung(
        brutto, bezahlter_betrag(zahlungen) + body.betrag, rechnung.status, gutschriften
    )
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
    rechnung = await _rechnung_laden(session, auth, rechnung_id)
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

    gegenbuchung = RechnungZahlung(
        mandant_id=rechnung.mandant_id,
        rechnung_id=rechnung_id,
        betrag=-original.betrag,
        datum=date.today(),
        erstellt_von=auth.user_id,
        notiz=f"Storno der Zahlung vom {original.datum.strftime('%d.%m.%Y')}",
        storniert_zahlung_id=zahlung_id,
    )
    session.add(gegenbuchung)
    await session.flush()
    await _audit(
        session, auth, "zahlung_storniert", rechnung,
        zahlung_id=str(zahlung_id), gegenbuchung_id=str(gegenbuchung.id), betrag=str(original.betrag),
    )

    positionen = await positionen_fuer(session, rechnung_id)
    zahlungen = await zahlungen_fuer(session, rechnung_id)
    brutto = brutto_betrag(rechnung, positionen)
    bezahlt = bezahlter_betrag(zahlungen)
    gutschriften = await rechnungsart_service.gutschrift_summe(session, rechnung_id)
    if bezahlt <= 0 and gutschriften <= 0:
        rechnung.status = "versendet"
        rechnung.bezahlt_am = None
    elif brutto - bezahlt - gutschriften > 0:
        rechnung.status = "teilweise_bezahlt" if bezahlt > 0 else "versendet"
        rechnung.bezahlt_am = None
    # Sonst bleibt "bezahlt" -- praktisch nur bei einem Storno, das den
    # offenen Betrag nicht wirklich veraendert, oder wenn Gutschriften den
    # Rest decken.

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
    rechnung = await _rechnung_laden(session, auth, rechnung_id, geloeschte_zulassen=True)
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
    rechnung = await _rechnung_laden(session, auth, rechnung_id, geloeschte_zulassen=True)
    if not rechnung.xml_object_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Keine ZUGFeRD-XML fuer diese Rechnung vorhanden")
    xml_bytes = await storage_service.download_bytes(rechnung.xml_object_key)
    # Die XRechnung ist die Rechnung selbst und wird einzeln weitergegeben; der feste
    # Name "factur-x.xml" steht fuer die im ZUGFeRD-PDF eingebettete Datei.
    dateiname = (
        f"{rechnung.rechnungsnummer}-xrechnung.xml" if rechnung.e_rechnung_profil == "xrechnung" else "factur-x.xml"
    )
    return Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": f'inline; filename="{dateiname}"'},
    )


@router.get("/{rechnung_id}/emails", response_model=list[EmailLogRead])
async def list_rechnung_emails(
    rechnung_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[EmailLog]:
    rechnung = await _rechnung_laden(session, auth, rechnung_id)
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
    rechnung = await _rechnung_laden(session, auth, rechnung_id)
    kunde = await session.get(Kunde, rechnung.kunde_id)
    mandant = await session.get(Mandant, auth.mandant_id)
    storniert_rechnung = await _storniert_rechnung_fuer(session, rechnung)
    pdf_bytes = await pdf_bytes_fuer(session, rechnung, mandant, kunde, storniert_rechnung=storniert_rechnung)
    dateiname = f"{rechnung.rechnungsnummer}.pdf"
    # XRechnung: Empfaenger (Behoerden, Eingangsportale) verarbeiten die XML, nicht das PDF.
    weitere_anhaenge = []
    if rechnung.e_rechnung_profil == "xrechnung" and rechnung.xml_object_key:
        xml_bytes = await storage_service.download_bytes(rechnung.xml_object_key)
        weitere_anhaenge.append((f"{rechnung.rechnungsnummer}-xrechnung.xml", xml_bytes, "application/xml"))

    log = await send_email_and_log(
        session,
        auth.mandant_id,
        entity_type="rechnung",
        entity_id=rechnung_id,
        to=body.empfaenger,
        subject=body.betreff or f"{rechnungsart_service.rechnungsart_label(rechnung)} {rechnung.rechnungsnummer}",
        body=body.inhalt
        or f"Anbei erhalten Sie unsere {rechnungsart_service.rechnungsart_label(rechnung)} {rechnung.rechnungsnummer}.",
        gesendet_von=auth.user_id,
        attachment=(dateiname, pdf_bytes, "application/pdf"),
        weitere_anhaenge=weitere_anhaenge,
    )
    await _audit(session, auth, "rechnung_email_versendet", rechnung, email_log_id=str(log.id), status=log.status)
    return log
