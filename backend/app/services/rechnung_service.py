from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.rechnung import Rechnung, RechnungPosition, RechnungZahlung
from app.schemas.rechnung import RechnungPositionRead, RechnungRead, RechnungZahlungRead
from app.services import pdf_service, storage_service
from app.services.numbering_service import next_rechnungsnummer

_CENT = Decimal("0.01")


async def positionen_fuer(session: AsyncSession, rechnung_id: UUID) -> list[RechnungPosition]:
    result = await session.execute(
        select(RechnungPosition)
        .where(RechnungPosition.rechnung_id == rechnung_id)
        .order_by(RechnungPosition.position)
    )
    return list(result.scalars().all())


def netto_betrag(rechnung: Rechnung, positionen: list[RechnungPosition]) -> Decimal:
    """Positionen (falls vorhanden) sind die Quelle der Wahrheit, dieselbe
    Ueberlegung wie bei Angebot.gesamt_netto: verhindert eine veraltete Summe
    nach nachtraeglicher Preisaenderung einer Position. Ohne Positionen (der
    einfache Fall aus Phase 6, eine Abschlussrechnung ohne eigene Zeilen)
    bleibt der manuell gesetzte betrag_netto massgeblich."""
    if positionen:
        return sum((p.menge * p.einzelpreis for p in positionen), Decimal("0")).quantize(_CENT)
    return rechnung.betrag_netto.quantize(_CENT)


async def zahlungen_fuer(session: AsyncSession, rechnung_id: UUID) -> list[RechnungZahlung]:
    result = await session.execute(
        select(RechnungZahlung)
        .where(RechnungZahlung.rechnung_id == rechnung_id)
        .order_by(RechnungZahlung.datum, RechnungZahlung.created_at)
    )
    return list(result.scalars().all())


async def zahlungen_fuer_mehrere(
    session: AsyncSession, rechnung_ids: list[UUID]
) -> dict[UUID, list[RechnungZahlung]]:
    """Bulk-Pendant zu positionen_fuer_mehrere -- dieselbe N+1-Vermeidung."""
    if not rechnung_ids:
        return {}
    result = await session.execute(
        select(RechnungZahlung)
        .where(RechnungZahlung.rechnung_id.in_(rechnung_ids))
        .order_by(RechnungZahlung.rechnung_id, RechnungZahlung.datum, RechnungZahlung.created_at)
    )
    gruppiert: dict[UUID, list[RechnungZahlung]] = {rid: [] for rid in rechnung_ids}
    for zahlung in result.scalars().all():
        gruppiert[zahlung.rechnung_id].append(zahlung)
    return gruppiert


def bezahlter_betrag(zahlungen: list[RechnungZahlung]) -> Decimal:
    return sum((z.betrag for z in zahlungen), Decimal("0")).quantize(_CENT)


def brutto_betrag(rechnung: Rechnung, positionen: list[RechnungPosition]) -> Decimal:
    netto = netto_betrag(rechnung, positionen)
    return (netto + netto * rechnung.mwst_satz / Decimal("100")).quantize(_CENT)


def status_nach_zahlung(brutto: Decimal, bezahlt: Decimal, aktueller_status: str) -> str:
    """Die einzige Stelle, die entscheidet, ob eine Rechnung nach einer
    Zahlungsbuchung versendet/teilweise_bezahlt/bezahlt ist -- Zahlungen
    fuehren den Status, nicht der Nutzer. entwurf/storniert werden hier nie
    hereingegeben (siehe Aufrufer-Gates in den Routen)."""
    offen = brutto - bezahlt
    if offen <= 0:
        return "bezahlt"
    if bezahlt > 0:
        return "teilweise_bezahlt"
    return aktueller_status


def netto_sql():
    """Netto als SQL-Ausdruck -- Gegenstueck zu netto_betrag() fuer alles, was
    in der Datenbank gefiltert, sortiert oder summiert werden muss (Betrags-
    filter und Summenzeile der Rechnungsuebersicht). Muss dieselbe Regel
    abbilden: Positionen gewinnen, sonst der manuell gesetzte betrag_netto.
    sum() ueber 0 Zeilen ist NULL, daher coalesce. round(...,2): die
    Positionssumme menge*einzelpreis vergroessert in Postgres die Skala
    (Numeric(10,2) * Numeric(10,2) -> Skala 4), sonst zeigt die Summenzeile
    z.B. "3450.0000" statt "3450.00"."""
    positionen_summe = (
        select(func.sum(RechnungPosition.menge * RechnungPosition.einzelpreis))
        .where(RechnungPosition.rechnung_id == Rechnung.id)
        .correlate(Rechnung)
        .scalar_subquery()
    )
    return func.round(func.coalesce(positionen_summe, Rechnung.betrag_netto), 2)


def brutto_sql():
    """Brutto als SQL-Ausdruck. Brutto ist absichtlich nirgends persistiert
    (siehe RechnungRead.betrag_brutto) -- fuers Filtern/Sortieren nach Betrag
    braucht es die Formel trotzdem in SQL, statt eine redundante Spalte
    einzufuehren, die gegen netto_betrag() auseinanderlaufen koennte."""
    return func.round(
        netto_sql() * (Decimal("1") + Rechnung.mwst_satz / Decimal("100")), 2
    )


def bezahlt_sql():
    """Summe der Zahlungen als SQL-Ausdruck -- Gegenstueck zu
    RechnungRead.bezahlter_betrag. Negative Gegenbuchungen (Zahlungs-Storno)
    rechnen sich hier arithmetisch von selbst heraus."""
    zahlungen_summe = (
        select(func.sum(RechnungZahlung.betrag))
        .where(RechnungZahlung.rechnung_id == Rechnung.id)
        .correlate(Rechnung)
        .scalar_subquery()
    )
    return func.coalesce(zahlungen_summe, Decimal("0"))


def offen_sql():
    """Offener Betrag als SQL-Ausdruck -- brutto_sql() minus bezahlt_sql().
    Fuer die Summenzeile/den nur_offen-Filter der Uebersicht: reicht NICHT,
    einfach den vollen Bruttobetrag zu nehmen, sobald es teilweise_bezahlt
    gibt -- sonst zaehlt eine zu 90% bezahlte Rechnung als voll offen."""
    return brutto_sql() - bezahlt_sql()


async def positionen_fuer_mehrere(
    session: AsyncSession, rechnung_ids: list[UUID]
) -> dict[UUID, list[RechnungPosition]]:
    """Eine Query fuer alle Positionen einer Seite statt einer pro Zeile --
    die Uebersicht liefert bis zu 200 Rechnungen, positionen_fuer() waere
    dort ein N+1."""
    if not rechnung_ids:
        return {}
    result = await session.execute(
        select(RechnungPosition)
        .where(RechnungPosition.rechnung_id.in_(rechnung_ids))
        .order_by(RechnungPosition.rechnung_id, RechnungPosition.position)
    )
    gruppiert: dict[UUID, list[RechnungPosition]] = {rid: [] for rid in rechnung_ids}
    for position in result.scalars().all():
        gruppiert[position.rechnung_id].append(position)
    return gruppiert


async def kunden_namen_fuer(
    session: AsyncSession, kunde_ids: list[UUID]
) -> dict[UUID, str]:
    """Ein Lookup fuer alle Kundennamen einer Seite -- die Uebersicht und der
    CSV-Export brauchen den Namen je Zeile, ein session.get() pro Zeile waere
    erneut ein N+1."""
    if not kunde_ids:
        return {}
    result = await session.execute(
        select(Kunde.id, Kunde.name).where(Kunde.id.in_(set(kunde_ids)))
    )
    return {kunde_id: name for kunde_id, name in result.all()}


_AUSGESCHLOSSENE_FELDER = (
    "positionen",
    "zahlungen",
    "betrag_netto",
    "betrag_brutto",
    "bezahlter_betrag",
    "offener_betrag",
    "ist_ueberfaellig",
    "tage_ueberfaellig",
)


def _read_model_aus(
    rechnung: Rechnung, positionen: list[RechnungPosition], zahlungen: list[RechnungZahlung]
) -> RechnungRead:
    return RechnungRead(
        **{k: getattr(rechnung, k) for k in RechnungRead.model_fields if k not in _AUSGESCHLOSSENE_FELDER},
        betrag_netto=netto_betrag(rechnung, positionen),
        positionen=[RechnungPositionRead.model_validate(p) for p in positionen],
        zahlungen=[RechnungZahlungRead.model_validate(z) for z in zahlungen],
    )


async def to_read_model_bulk(
    session: AsyncSession, rechnungen: list[Rechnung]
) -> list[RechnungRead]:
    ids = [r.id for r in rechnungen]
    positionen_je_rechnung = await positionen_fuer_mehrere(session, ids)
    zahlungen_je_rechnung = await zahlungen_fuer_mehrere(session, ids)
    return [
        _read_model_aus(r, positionen_je_rechnung.get(r.id, []), zahlungen_je_rechnung.get(r.id, []))
        for r in rechnungen
    ]


async def to_read_model(session: AsyncSession, rechnung: Rechnung) -> RechnungRead:
    positionen = await positionen_fuer(session, rechnung.id)
    zahlungen = await zahlungen_fuer(session, rechnung.id)
    return _read_model_aus(rechnung, positionen, zahlungen)


async def erstelle_stornorechnung(
    session: AsyncSession, original: Rechnung, actor_user_id: UUID
) -> Rechnung:
    """GoBD verbietet, eine einmal versendete Rechnung nachtraeglich zu
    aendern oder zu loeschen -- die Korrektur braucht einen eigenen,
    referenzierten Gegenbeleg (Positionen mit umgekehrtem Vorzeichen) statt
    eines simplen Status-Flips auf 'storniert'. Die Stornorechnung erhaelt
    die naechste Nummer aus demselben "R-"-Nummernkreis wie normale
    Rechnungen (rechtlich zulaessig, siehe next_rechnungsnummer) und ist ab
    dem Moment ihrer Entstehung bereits als versendet zu behandeln."""
    original_positionen = await positionen_fuer(session, original.id)
    rechnungsnummer = await next_rechnungsnummer(session, original.mandant_id)
    jetzt = datetime.now(timezone.utc)

    storno = Rechnung(
        mandant_id=original.mandant_id,
        kunde_id=original.kunde_id,
        vorgang_id=original.vorgang_id,
        rechnungsnummer=rechnungsnummer,
        betrag_netto=-netto_betrag(original, original_positionen),
        mwst_satz=original.mwst_satz,
        leistungsdatum=original.leistungsdatum,
        status="versendet",
        versendet_am=jetzt,
        erstellt_von=actor_user_id,
        ist_storno=True,
        storniert_rechnung_id=original.id,
    )
    session.add(storno)
    await session.flush()

    for p in original_positionen:
        session.add(
            RechnungPosition(
                mandant_id=original.mandant_id,
                rechnung_id=storno.id,
                position=p.position,
                beschreibung=p.beschreibung,
                menge=p.menge,
                einheit=p.einheit,
                einzelpreis=-p.einzelpreis,
            )
        )

    original.status = "storniert"
    await session.flush()
    await session.refresh(storno)
    return storno


async def archiviere_pdf(
    session: AsyncSession,
    rechnung: Rechnung,
    mandant: Mandant,
    kunde: Kunde,
    storniert_rechnung: Rechnung | None = None,
) -> bytes:
    """Erzeugt das PDF einmalig zum Versand-Zeitpunkt und speichert es
    unveraenderlich in MinIO/S3 -- spaetere Aenderungen an Firmendaten/Logo
    duerfen das bereits verschickte Dokument nicht nachtraeglich veraendern
    (GoBD-Unveraenderbarkeitsgrundsatz). Gibt die PDF-Bytes zurueck, damit
    der Aufrufer sie z.B. direkt als E-Mail-Anhang weiterverwenden kann,
    ohne sie erneut aus MinIO abzurufen."""
    positionen = await positionen_fuer(session, rechnung.id)
    pdf_bytes = pdf_service.generate_rechnung_pdf(
        mandant, rechnung, kunde, positionen, storniert_rechnung=storniert_rechnung
    )
    key = storage_service.new_rechnung_pdf_key(rechnung.id)
    await storage_service.upload_bytes(key, pdf_bytes, "application/pdf")
    rechnung.pdf_object_key = key
    return pdf_bytes


async def pdf_bytes_fuer(
    session: AsyncSession,
    rechnung: Rechnung,
    mandant: Mandant,
    kunde: Kunde,
    storniert_rechnung: Rechnung | None = None,
) -> bytes:
    """Liefert exakt das archivierte PDF, sobald eines existiert (ab dem
    Versand) -- nur fuer einen noch nicht versendeten Entwurf wird live neu
    generiert, weil dort noch kein unveraenderliches Abbild existieren kann."""
    if rechnung.pdf_object_key:
        return await storage_service.download_bytes(rechnung.pdf_object_key)
    positionen = await positionen_fuer(session, rechnung.id)
    return pdf_service.generate_rechnung_pdf(
        mandant, rechnung, kunde, positionen, storniert_rechnung=storniert_rechnung
    )
