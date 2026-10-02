import csv
import io
import zlib
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.eingangsrechnung import Eingangsrechnung
from app.models.kunde import Kunde
from app.models.lieferant import Lieferant
from app.models.rechnung import Rechnung
from app.schemas.auswertung import (
    OffenePostenBericht,
    OffenePostenBucket,
    OffenerPostenEintrag,
    UstVaBericht,
    UstVaSatzZeile,
)
from app.services import eingangsrechnung_service, rechnung_service

_CENT = Decimal("0.01")

# SKR03-orientierte Standard-Kontenrahmen fuer den DATEV-Export -- ein
# Startpunkt, kein zertifizierter Buchungsvorschlag. Ein Steuerberater muss
# vor dem ersten echten Import pruefen, ob die Konten/BU-Schluessel zum
# tatsaechlich verwendeten Kontenrahmen des Mandanten passen.
_ERLOESKONTO_NACH_SATZ = {Decimal("19.00"): "8400", Decimal("7.00"): "8300"}
_ERLOES_BU_SCHLUESSEL = {Decimal("19.00"): "3", Decimal("7.00"): "2"}
_AUFWANDSKONTO_NACH_KATEGORIE = {
    "wareneinkauf": "3200",
    "betriebskosten": "4900",
    "miete": "4210",
    "personal": "4120",
    "fahrzeug": "4530",
    "versicherung": "4360",
    "sonstiges": "4900",
}
_VORSTEUER_BU_SCHLUESSEL = {Decimal("19.00"): "9", Decimal("7.00"): "8"}


def _tagesbeginn_utc(tag: date) -> datetime:
    return datetime.combine(tag, time.min, tzinfo=timezone.utc)


def _debitorenkonto(kunde_id: UUID) -> str:
    """Kein Kontenrahmen im System hinterlegt -- die Kontonummer wird
    stabil aus der Kunden-ID abgeleitet (gleicher Kunde = gleiches Konto
    ueber mehrere Exporte hinweg), im ueblichen Debitoren-Nummernkreis."""
    return str(10000 + (zlib.crc32(kunde_id.bytes) % 9000))


def _kreditorenkonto(lieferant_id: UUID | None, lieferant_name: str) -> str:
    schluessel = lieferant_id.bytes if lieferant_id else lieferant_name.encode("utf-8")
    return str(70000 + (zlib.crc32(schluessel) % 9000))


async def ust_va_bericht(session: AsyncSession, mandant_id: UUID, von: date, bis: date) -> UstVaBericht:
    """Aggregiert Umsatzsteuer (aus versendeten Ausgangsrechnungen, inkl.
    Storno-Belegen mit negativen Betraegen -- siehe Rechnung.ist_storno)
    und Vorsteuer (aus nicht stornierten Eingangsrechnungen) je Steuersatz
    fuer den angegebenen Zeitraum. Massgeblich ist bei Ausgangsrechnungen
    versendet_am (Soll-Versteuerung: der Zeitpunkt der Leistungserbringung/
    Rechnungsstellung, nicht der Zahlung), bei Eingangsrechnungen das vom
    Aussteller angegebene rechnungsdatum."""
    ausgang_stmt = select(Rechnung).where(
        Rechnung.mandant_id == mandant_id,
        Rechnung.versendet_am.isnot(None),
        Rechnung.versendet_am >= _tagesbeginn_utc(von),
        Rechnung.versendet_am < _tagesbeginn_utc(bis + timedelta(days=1)),
    )
    ausgangsrechnungen = (await session.execute(ausgang_stmt)).scalars().all()

    umsatz_nach_satz: dict[Decimal, Decimal] = {}
    for rechnung in ausgangsrechnungen:
        positionen = await rechnung_service.positionen_fuer(session, rechnung.id)
        netto = rechnung_service.netto_betrag(rechnung, positionen)
        umsatz_nach_satz[rechnung.mwst_satz] = umsatz_nach_satz.get(rechnung.mwst_satz, Decimal("0")) + netto

    eingang_stmt = select(Eingangsrechnung).where(
        Eingangsrechnung.mandant_id == mandant_id,
        Eingangsrechnung.status != "storniert",
        Eingangsrechnung.rechnungsdatum >= von,
        Eingangsrechnung.rechnungsdatum <= bis,
    )
    eingangsrechnungen = (await session.execute(eingang_stmt)).scalars().all()

    vorsteuer_netto_nach_satz: dict[Decimal, Decimal] = {}
    for eingangsrechnung in eingangsrechnungen:
        positionen = await eingangsrechnung_service.positionen_fuer(session, eingangsrechnung.id)
        netto = eingangsrechnung_service.netto_betrag(eingangsrechnung, positionen)
        vorsteuer_netto_nach_satz[eingangsrechnung.mwst_satz] = (
            vorsteuer_netto_nach_satz.get(eingangsrechnung.mwst_satz, Decimal("0")) + netto
        )

    umsatzsteuer_saetze = [
        UstVaSatzZeile(satz=satz, netto=netto.quantize(_CENT), steuer=(netto * satz / Decimal("100")).quantize(_CENT))
        for satz, netto in sorted(umsatz_nach_satz.items())
    ]
    vorsteuer_saetze = [
        UstVaSatzZeile(satz=satz, netto=netto.quantize(_CENT), steuer=(netto * satz / Decimal("100")).quantize(_CENT))
        for satz, netto in sorted(vorsteuer_netto_nach_satz.items())
    ]
    summe_umsatzsteuer = sum((z.steuer for z in umsatzsteuer_saetze), Decimal("0")).quantize(_CENT)
    summe_vorsteuer = sum((z.steuer for z in vorsteuer_saetze), Decimal("0")).quantize(_CENT)

    return UstVaBericht(
        von=von,
        bis=bis,
        umsatzsteuer_saetze=umsatzsteuer_saetze,
        vorsteuer_saetze=vorsteuer_saetze,
        summe_umsatzsteuer=summe_umsatzsteuer,
        summe_vorsteuer=summe_vorsteuer,
        zahllast=(summe_umsatzsteuer - summe_vorsteuer).quantize(_CENT),
    )


_BUCKET_REIHENFOLGE = ["Nicht fällig", "1-30 Tage", "31-60 Tage", "61-90 Tage", "90+ Tage"]


def _bucket_label(tage_ueberfaellig: int) -> str:
    if tage_ueberfaellig <= 0:
        return "Nicht fällig"
    if tage_ueberfaellig <= 30:
        return "1-30 Tage"
    if tage_ueberfaellig <= 60:
        return "31-60 Tage"
    if tage_ueberfaellig <= 90:
        return "61-90 Tage"
    return "90+ Tage"


def _buckets_aus(eintraege: list[OffenerPostenEintrag]) -> list[OffenePostenBucket]:
    summen = {label: Decimal("0") for label in _BUCKET_REIHENFOLGE}
    anzahl = {label: 0 for label in _BUCKET_REIHENFOLGE}
    for eintrag in eintraege:
        label = _bucket_label(eintrag.tage_ueberfaellig)
        summen[label] += eintrag.offener_betrag
        anzahl[label] += 1
    return [
        OffenePostenBucket(label=label, anzahl=anzahl[label], summe=summen[label].quantize(_CENT))
        for label in _BUCKET_REIHENFOLGE
        if anzahl[label] > 0
    ]


async def offene_posten_bericht(session: AsyncSession, mandant_id: UUID, heute: date) -> OffenePostenBericht:
    """OP-Liste: fasst offene Debitoren (Ausgangsrechnungen) und Kreditoren
    (Eingangsrechnungen) in einem gemeinsamen Alterungsraster zusammen.
    Entwuerfe zaehlen bewusst nicht mit -- fuer eine noch nicht versendete
    Rechnung gibt es nichts zu mahnen oder zu bezahlen."""
    debitoren_stmt = select(
        Rechnung.id,
        Rechnung.rechnungsnummer,
        Rechnung.kunde_id,
        Rechnung.faellig_am,
        rechnung_service.offen_sql().label("offen"),
    ).where(Rechnung.mandant_id == mandant_id, Rechnung.status.in_(("versendet", "teilweise_bezahlt")))
    debitor_zeilen = [row for row in (await session.execute(debitoren_stmt)).all() if row.offen > 0]
    kunden_namen = await rechnung_service.kunden_namen_fuer(session, [row.kunde_id for row in debitor_zeilen])

    debitoren = [
        OffenerPostenEintrag(
            id=row.id,
            nummer=row.rechnungsnummer,
            partner_name=kunden_namen.get(row.kunde_id, "?"),
            faellig_am=row.faellig_am,
            tage_ueberfaellig=max((heute - row.faellig_am).days, 0) if row.faellig_am else 0,
            offener_betrag=row.offen,
        )
        for row in debitor_zeilen
    ]
    debitoren.sort(key=lambda e: -e.tage_ueberfaellig)

    eingang_stmt = select(Eingangsrechnung).where(
        Eingangsrechnung.mandant_id == mandant_id, Eingangsrechnung.status == "offen"
    )
    eingangsrechnungen = (await session.execute(eingang_stmt)).scalars().all()

    kreditoren: list[OffenerPostenEintrag] = []
    for eingangsrechnung in eingangsrechnungen:
        positionen = await eingangsrechnung_service.positionen_fuer(session, eingangsrechnung.id)
        zahlungen = await eingangsrechnung_service.zahlungen_fuer(session, eingangsrechnung.id)
        brutto = eingangsrechnung_service.brutto_betrag(eingangsrechnung, positionen)
        offen = brutto - eingangsrechnung_service.bezahlter_betrag(zahlungen)
        if offen <= 0:
            continue
        faellig_am = eingangsrechnung.faellig_am
        kreditoren.append(
            OffenerPostenEintrag(
                id=eingangsrechnung.id,
                nummer=eingangsrechnung.rechnungsnummer_lieferant,
                partner_name=eingangsrechnung.lieferant_name,
                faellig_am=faellig_am,
                tage_ueberfaellig=max((heute - faellig_am).days, 0) if faellig_am else 0,
                offener_betrag=offen,
            )
        )
    kreditoren.sort(key=lambda e: -e.tage_ueberfaellig)

    return OffenePostenBericht(
        debitoren=debitoren,
        kreditoren=kreditoren,
        summe_debitoren=sum((e.offener_betrag for e in debitoren), Decimal("0")).quantize(_CENT),
        summe_kreditoren=sum((e.offener_betrag for e in kreditoren), Decimal("0")).quantize(_CENT),
        debitoren_buckets=_buckets_aus(debitoren),
        kreditoren_buckets=_buckets_aus(kreditoren),
    )


def _betrag_datev(betrag: Decimal) -> str:
    """DATEV verlangt Komma statt Punkt als Dezimaltrennzeichen und immer
    ein positives Vorzeichen -- die Richtung ergibt sich ausschliesslich
    aus dem Soll/Haben-Kennzeichen, nicht aus dem Vorzeichen des Betrags."""
    return f"{abs(betrag):.2f}".replace(".", ",")


async def datev_export_csv(session: AsyncSession, mandant_id: UUID, von: date, bis: date) -> Response:
    """Buchungsstapel-CSV im DATEV-EXTF-Format (siehe Modul-Docstring-
    Kommentare zu den Kontenrahmen-Annahmen). Nur als Ausgangspunkt fuer
    den Steuerberater gedacht -- vor dem ersten echten Import unbedingt
    gegen den tatsaechlichen Kontenrahmen des Mandanten pruefen."""
    ausgang_stmt = select(Rechnung).where(
        Rechnung.mandant_id == mandant_id,
        Rechnung.versendet_am.isnot(None),
        Rechnung.versendet_am >= _tagesbeginn_utc(von),
        Rechnung.versendet_am < _tagesbeginn_utc(bis + timedelta(days=1)),
    ).order_by(Rechnung.versendet_am)
    ausgangsrechnungen = (await session.execute(ausgang_stmt)).scalars().all()

    eingang_stmt = select(Eingangsrechnung).where(
        Eingangsrechnung.mandant_id == mandant_id,
        Eingangsrechnung.status != "storniert",
        Eingangsrechnung.rechnungsdatum >= von,
        Eingangsrechnung.rechnungsdatum <= bis,
    ).order_by(Eingangsrechnung.rechnungsdatum)
    eingangsrechnungen = (await session.execute(eingang_stmt)).scalars().all()

    zeilen: list[list[str]] = []
    for rechnung in ausgangsrechnungen:
        kunde = await session.get(Kunde, rechnung.kunde_id)
        positionen = await rechnung_service.positionen_fuer(session, rechnung.id)
        netto = rechnung_service.netto_betrag(rechnung, positionen)
        brutto = (netto + netto * rechnung.mwst_satz / Decimal("100")).quantize(_CENT)
        zeilen.append(
            [
                _betrag_datev(brutto),
                "S",
                "EUR",
                _debitorenkonto(rechnung.kunde_id),
                _ERLOESKONTO_NACH_SATZ.get(rechnung.mwst_satz, "8400"),
                _ERLOES_BU_SCHLUESSEL.get(rechnung.mwst_satz, ""),
                rechnung.versendet_am.strftime("%d%m"),
                rechnung.rechnungsnummer,
                "",
                f"Rechnung {rechnung.rechnungsnummer} {kunde.name if kunde else ''}".strip(),
            ]
        )
    for eingangsrechnung in eingangsrechnungen:
        positionen = await eingangsrechnung_service.positionen_fuer(session, eingangsrechnung.id)
        netto = eingangsrechnung_service.netto_betrag(eingangsrechnung, positionen)
        brutto = (netto + netto * eingangsrechnung.mwst_satz / Decimal("100")).quantize(_CENT)
        zeilen.append(
            [
                _betrag_datev(brutto),
                "S",
                "EUR",
                _AUFWANDSKONTO_NACH_KATEGORIE.get(eingangsrechnung.kategorie or "sonstiges", "4900"),
                _kreditorenkonto(eingangsrechnung.lieferant_id, eingangsrechnung.lieferant_name),
                _VORSTEUER_BU_SCHLUESSEL.get(eingangsrechnung.mwst_satz, ""),
                eingangsrechnung.rechnungsdatum.strftime("%d%m"),
                eingangsrechnung.rechnungsnummer_lieferant,
                "",
                f"Eingangsrechnung {eingangsrechnung.rechnungsnummer_lieferant} {eingangsrechnung.lieferant_name}".strip(),
            ]
        )

    jetzt = datetime.now(timezone.utc)
    header_zeile = [
        "EXTF", "510", "21", "Buchungsstapel", "7",
        jetzt.strftime("%Y%m%d%H%M%S%f")[:-3],
        "", "", "", "",
        "1001", "1",
        f"{von.year}0101",
        "4",
        von.strftime("%Y%m%d"), bis.strftime("%Y%m%d"),
        "", "", "1", "0", "0", "EUR",
    ]
    spalten_header = [
        "Umsatz (ohne Soll/Haben-Kz)", "Soll/Haben-Kennzeichen", "WKZ Umsatz",
        "Konto", "Gegenkonto (ohne BU-Schlüssel)", "BU-Schlüssel",
        "Belegdatum", "Belegfeld 1", "Belegfeld 2", "Buchungstext",
    ]

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(header_zeile)
    writer.writerow(spalten_header)
    writer.writerows(zeilen)

    return Response(
        content=buffer.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="EXTF_Buchungsstapel_{von.isoformat()}_{bis.isoformat()}.csv"'
        },
    )
