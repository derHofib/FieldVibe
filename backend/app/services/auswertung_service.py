from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.eingangsrechnung import Eingangsrechnung
from app.models.kunde import Kunde
from app.models.lieferant import Lieferant
from app.models.mandant import Mandant
from app.models.rechnung import Rechnung
from app.schemas.auswertung import (
    OffenePostenBericht,
    OffenePostenBucket,
    OffenerPostenEintrag,
    UstVaBericht,
    UstVaKategorieZeile,
    UstVaSatzZeile,
)
from app.services import datev_service, eingangsrechnung_service, rechnung_service, steuer_service

_CENT = Decimal("0.01")

# Standardkonten je Kontenrahmen stehen in datev_service -- ein Startpunkt,
# kein zertifizierter Buchungsvorschlag. Die Erloeskonten je Steuergruppe sind
# je Mandant ueberschreibbar (firmendaten.buchhaltung); Defaults gibt es nur
# fuer S/19, S/7 und Kleinunternehmer-E.
_ERLOES_BU_SCHLUESSEL = {Decimal("19.00"): "3", Decimal("7.00"): "2"}
_UST_VA_BEZEICHNUNG = {
    "AE": "Steuerpflichtige Umsätze, Steuerschuldner ist der Leistungsempfänger (§ 13b)",
    "Z": "Umsätze zum Steuersatz 0 % (§ 12 Abs. 3)",
    "E": "Sonstige steuerfreie Umsätze",
}
_VORSTEUER_BU_SCHLUESSEL = {Decimal("19.00"): "9", Decimal("7.00"): "8"}


def _tagesbeginn_utc(tag: date) -> datetime:
    return datetime.combine(tag, time.min, tzinfo=timezone.utc)


class KontoNichtKonfiguriert(Exception):
    """Fuer eine Steuergruppe ist kein Erloeskonto hinterlegt -- die Route macht
    daraus ein 422. Z, AE und E (ausser Kleinunternehmer) haben bewusst keinen
    Default: ein geratenes Konto wuerde still falsch buchen."""

    def __init__(self, kategorie: str, schluessel: str):
        self.kategorie = kategorie
        self.schluessel = schluessel
        super().__init__(
            f"Für Steuerkategorie {kategorie} ist kein Erlöskonto hinterlegt – "
            f"bitte unter Firmendaten ➝ Buchhaltung eintragen (Schlüssel {schluessel})"
        )


def _ist_kleinunternehmer_gruppe(mandant: Mandant, gruppe: steuer_service.SteuerGruppe) -> bool:
    # Der Grund am Beleg zaehlt mit: ein Mandant, der den Status spaeter verliert,
    # hat Altbelege, die weiterhin Kleinunternehmer-Belege sind.
    return gruppe.kategorie == "E" and (
        steuer_service.ist_kleinunternehmer(mandant) or gruppe.gruende == ("kleinunternehmer_19",)
    )


def _erloeskonto(
    mandant: Mandant, gruppe: steuer_service.SteuerGruppe, stammdaten: datev_service.DatevStammdaten
) -> tuple[str, str]:
    """(Konto, BU-Schluessel) einer Steuergruppe aus firmendaten.buchhaltung,
    sonst der Default des Kontenrahmens."""
    schluessel = f"{gruppe.kategorie}:{gruppe.satz:f}"
    eintrag = ((mandant.firmendaten or {}).get("buchhaltung") or {}).get("erloeskonten", {}).get(schluessel)
    standard = datev_service.ERLOESKONTO_NACH_SATZ[stammdaten.kontenrahmen]
    if eintrag and eintrag.get("konto"):
        konto = datev_service.sachkonto(str(eintrag["konto"]), stammdaten, bezeichnung=f"Erlöskonto {schluessel}")
        return konto, str(eintrag.get("bu") or "")
    if gruppe.kategorie == "S":
        konto4 = standard.get(f"{gruppe.satz:f}", standard["19.00"])
        return datev_service.standardkonto(konto4, stammdaten), _ERLOES_BU_SCHLUESSEL.get(gruppe.satz, "")
    if _ist_kleinunternehmer_gruppe(mandant, gruppe):
        konto4 = datev_service.KLEINUNTERNEHMER_ERLOESKONTO[stammdaten.kontenrahmen]
        return datev_service.standardkonto(konto4, stammdaten), ""
    raise KontoNichtKonfiguriert(gruppe.kategorie, schluessel)


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

    mandant = await session.get(Mandant, mandant_id)
    umsatz_nach_satz: dict[Decimal, Decimal] = {}
    # Z/AE und E ausser Kleinunternehmer haben keine Steuer und stehen in
    # eigenen Zeilen; die Zuordnung zu Kennzahlen macht der Steuerberater.
    umsatz_nach_kategorie: dict[str, Decimal] = {}
    for rechnung in ausgangsrechnungen:
        positionen = await rechnung_service.positionen_fuer(session, rechnung.id)
        for gruppe in steuer_service.steuer_gruppen(rechnung, positionen):
            if gruppe.kategorie in ("Z", "AE") or (
                gruppe.kategorie == "E" and not _ist_kleinunternehmer_gruppe(mandant, gruppe)
            ):
                umsatz_nach_kategorie[gruppe.kategorie] = (
                    umsatz_nach_kategorie.get(gruppe.kategorie, Decimal("0")) + gruppe.netto
                )
            else:
                umsatz_nach_satz[gruppe.satz] = umsatz_nach_satz.get(gruppe.satz, Decimal("0")) + gruppe.netto

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
        UstVaSatzZeile(satz=satz, netto=netto.quantize(_CENT), steuer=steuer_service.runde_cent(netto * satz / Decimal("100")))
        for satz, netto in sorted(umsatz_nach_satz.items())
    ]
    vorsteuer_saetze = [
        UstVaSatzZeile(satz=satz, netto=netto.quantize(_CENT), steuer=(netto * satz / Decimal("100")).quantize(_CENT))
        for satz, netto in sorted(vorsteuer_netto_nach_satz.items())
    ]
    sonstige_umsaetze = [
        UstVaKategorieZeile(kategorie=kategorie, bezeichnung=_UST_VA_BEZEICHNUNG[kategorie], netto=netto.quantize(_CENT))
        for kategorie, netto in sorted(umsatz_nach_kategorie.items(), key=lambda e: list(_UST_VA_BEZEICHNUNG).index(e[0]))
    ]
    summe_umsatzsteuer = sum((z.steuer for z in umsatzsteuer_saetze), Decimal("0")).quantize(_CENT)
    summe_vorsteuer = sum((z.steuer for z in vorsteuer_saetze), Decimal("0")).quantize(_CENT)

    return UstVaBericht(
        von=von,
        bis=bis,
        umsatzsteuer_saetze=umsatzsteuer_saetze,
        sonstige_umsaetze=sonstige_umsaetze,
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





def _soll_haben_ausgang(brutto: Decimal) -> str:
    """Eine Ausgangsrechnung bucht Soll auf das Debitorenkonto. Storno-Belege
    und Gutschriften tragen negative Betraege und sind Gegenbuchungen: gleiche
    Konten, aber Haben. Ohne das erschiene ein Storno wie eine zweite
    Normalbuchung und der Umsatz waere doppelt gebucht."""
    return "H" if brutto < 0 else "S"


async def datev_export_csv(session: AsyncSession, mandant_id: UUID, von: date, bis: date) -> Response:
    """Buchungsstapel im DATEV-EXTF-Format (Details und offene Annahmen:
    docs/konzepte/DATEV.md). Nur als Ausgangspunkt fuer den Steuerberater
    gedacht -- vor dem ersten echten Import unbedingt gegen den tatsaechlichen
    Kontenrahmen des Mandanten pruefen."""
    mandant = await session.get(Mandant, mandant_id)
    # Zuerst, damit ein unvollstaendig eingerichteter Mandant nicht erst nach
    # dem Laden aller Belege (und der Kontenvergabe) scheitert.
    stammdaten = datev_service.stammdaten_lesen(mandant)

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

    # Papierkorb-Kunden/-Lieferanten bewusst eingeschlossen: ihre Belege stehen
    # weiter im Export und brauchen ihr Konto.
    kunden_ids = {r.kunde_id for r in ausgangsrechnungen}
    kunden = {
        k.id: k
        for k in (
            await session.execute(select(Kunde).where(Kunde.mandant_id == mandant_id, Kunde.id.in_(kunden_ids)))
        ).scalars()
    }
    await datev_service.debitorenkonten_vergeben(session, mandant_id, list(kunden.values()), stammdaten.sachkontenlaenge)

    lieferant_ids = {e.lieferant_id for e in eingangsrechnungen if e.lieferant_id}
    lieferanten = {
        li.id: li
        for li in (
            await session.execute(
                select(Lieferant).where(Lieferant.mandant_id == mandant_id, Lieferant.id.in_(lieferant_ids))
            )
        ).scalars()
    }
    await datev_service.kreditorenkonten_vergeben(
        session, mandant_id, list(lieferanten.values()), stammdaten.sachkontenlaenge
    )

    aufwandskonten = datev_service.AUFWANDSKONTO_NACH_KATEGORIE[stammdaten.kontenrahmen]
    buchungen: list[datev_service.Buchung] = []
    for rechnung in ausgangsrechnungen:
        kunde = kunden.get(rechnung.kunde_id)
        positionen = await rechnung_service.positionen_fuer(session, rechnung.id)
        # Eine Buchungszeile je Steuergruppe: Erloeskonto und BU-Schluessel
        # kommen aus der Mandantenkonfiguration bzw. den Defaults (_erloeskonto).
        # Einzelsatz-Belege ergeben wie bisher genau eine Zeile.
        for gruppe in steuer_service.steuer_gruppen(rechnung, positionen):
            konto, bu_schluessel = _erloeskonto(mandant, gruppe, stammdaten)
            buchungen.append(
                datev_service.Buchung(
                    betrag=datev_service.betrag(gruppe.brutto),
                    soll_haben=_soll_haben_ausgang(gruppe.brutto),
                    konto=kunde.debitorenkonto,
                    gegenkonto=konto,
                    bu_schluessel=bu_schluessel,
                    belegdatum=rechnung.versendet_am.date(),
                    belegfeld1=rechnung.rechnungsnummer,
                    buchungstext=f"{'Gutschrift' if rechnung.rechnungsart == 'gutschrift' else 'Rechnung'} "
                    f"{rechnung.rechnungsnummer} {kunde.name}",
                )
            )
    sammelkonto = datev_service.kreditoren_sammelkonto(stammdaten.sachkontenlaenge)
    for eingangsrechnung in eingangsrechnungen:
        positionen = await eingangsrechnung_service.positionen_fuer(session, eingangsrechnung.id)
        netto = eingangsrechnung_service.netto_betrag(eingangsrechnung, positionen)
        brutto = (netto + netto * eingangsrechnung.mwst_satz / Decimal("100")).quantize(_CENT)
        lieferant = lieferanten.get(eingangsrechnung.lieferant_id)
        aufwandskonto = aufwandskonten.get(eingangsrechnung.kategorie or "sonstiges", aufwandskonten["sonstiges"])
        buchungen.append(
            datev_service.Buchung(
                betrag=datev_service.betrag(brutto),
                soll_haben="S",
                konto=datev_service.standardkonto(aufwandskonto, stammdaten),
                gegenkonto=lieferant.kreditorenkonto if lieferant else sammelkonto,
                bu_schluessel=_VORSTEUER_BU_SCHLUESSEL.get(eingangsrechnung.mwst_satz, ""),
                belegdatum=eingangsrechnung.rechnungsdatum,
                belegfeld1=eingangsrechnung.rechnungsnummer_lieferant,
                buchungstext=f"Eingangsrechnung {eingangsrechnung.rechnungsnummer_lieferant} "
                f"{eingangsrechnung.lieferant_name}",
            )
        )

    inhalt = datev_service.csv_bytes(stammdaten, von, bis, datetime.now(timezone.utc), buchungen)
    return Response(
        content=inhalt,
        media_type="text/csv; charset=windows-1252",
        headers={
            "Content-Disposition": f'attachment; filename="EXTF_Buchungsstapel_{von.isoformat()}_{bis.isoformat()}.csv"'
        },
    )
