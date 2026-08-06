from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.rechnung import Rechnung, RechnungPosition
from app.schemas.rechnung import RechnungPositionRead, RechnungRead
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


async def to_read_model(session: AsyncSession, rechnung: Rechnung) -> RechnungRead:
    positionen = await positionen_fuer(session, rechnung.id)
    netto = netto_betrag(rechnung, positionen)
    return RechnungRead(
        **{
            k: getattr(rechnung, k)
            for k in RechnungRead.model_fields
            if k not in ("positionen", "betrag_netto", "betrag_brutto")
        },
        betrag_netto=netto,
        positionen=[RechnungPositionRead.model_validate(p) for p in positionen],
    )


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
