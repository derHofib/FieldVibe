import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from botocore.exceptions import ClientError
from lxml import etree
from sqlalchemy import and_, case, func, or_, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.kunde import Kunde
from app.models.leistungsverzeichnis import LeistungsverzeichnisPosition, LeistungsverzeichnisVerwendung
from app.models.mandant import Mandant
from app.models.material import Material, MaterialVerwendung
from app.models.rechnung import Rechnung, RechnungPosition, RechnungZahlung
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.models.zeiterfassung import Zeiterfassung
from app.models.zeiterfassung_aenderung import ZeiterfassungAenderung
from app.schemas.rechnung import (
    AngerechneterAbschlagRead,
    GutschriftKurzRead,
    RechnungPositionRead,
    RechnungPositionVorschlag,
    RechnungRead,
    RechnungSteuerGruppeRead,
    RechnungVorgangAuswahlPosten,
    RechnungVorgangKopf,
    RechnungZahlungRead,
)
from app.services.aufbewahrung_service import aufbewahrung_fuer
from app.services import e_invoice_service, pdf_service, privatkunden_service, steuer_service, storage_service
from app.services.numbering_service import next_rechnungsnummer

logger = logging.getLogger(__name__)

_CENT = Decimal("0.01")
_STUNDE = Decimal("3600")

# Stufe 4 (docs/konzepte/ZEITERFASSUNG.md Abschnitt 8): welche Kategorie(n)
# hinter einer "zeit"/"fahrzeit"/"fahrtkosten"-Rechnungsposition stecken.
# Eine Zeile kann Stunden UND km tragen (km auch an "auftrag"-Zeilen, Konzept
# Abschnitt 11) -- beide Anteile werden getrennt gesperrt: Stunden-Quellen
# (zeit, fahrzeit, leistung) ueber buchungsstatus/abgerechnet_rechnung_id,
# "fahrtkosten" nur ueber km_abgerechnet_rechnung_id (Migration 0097).
# "fahrtkosten" zieht sein km aus BEIDEN Kategorien, "zeit" rechnet alle
# "auftrag"-Zeilen nach Dauer ab, "fahrzeit" die eigenstaendigen Fahrten.
STUNDEN_QUELLEN = ("zeit", "fahrzeit", "leistung")


def _zeiterfassung_quelle_filter(quelle: str) -> list | None:
    if quelle == "zeit":
        return [Zeiterfassung.kategorie == "auftrag"]
    if quelle == "fahrzeit":
        return [Zeiterfassung.kategorie == "fahrzeit"]
    if quelle == "fahrtkosten":
        return [Zeiterfassung.kategorie.in_(("auftrag", "fahrzeit")), Zeiterfassung.km.is_not(None)]
    return None


def km_frei_bedingung():
    """km-Anteil noch abrechenbar: kein Verweis -- oder der Verweis zeigt auf
    einen im Papierkorb liegenden Entwurf (der Verweis bleibt dort fuers
    Wiederherstellen stehen, vgl. abgerechnet_rechnung_id bei 'gebucht')."""
    entwurf_im_papierkorb = select(Rechnung.id).where(
        Rechnung.status == "entwurf", Rechnung.geloescht_am.is_not(None)
    )
    return or_(
        Zeiterfassung.km_abgerechnet_rechnung_id.is_(None),
        Zeiterfassung.km_abgerechnet_rechnung_id.in_(entwurf_im_papierkorb),
    )


async def km_gesperrt(session: AsyncSession, eintrag: Zeiterfassung) -> bool:
    """Python-Gegenstueck zu km_frei_bedingung (GoBD-Sperre der Zeile, sobald
    EIN Anteil abgerechnet ist)."""
    if eintrag.km_abgerechnet_rechnung_id is None:
        return False
    rechnung = await session.get(Rechnung, eintrag.km_abgerechnet_rechnung_id)
    return not (rechnung is None or (rechnung.status == "entwurf" and rechnung.geloescht_am is not None))


async def positionen_fuer(session: AsyncSession, rechnung_id: UUID) -> list[RechnungPosition]:
    result = await session.execute(
        select(RechnungPosition)
        .where(RechnungPosition.rechnung_id == rechnung_id)
        .order_by(RechnungPosition.position)
    )
    return list(result.scalars().all())


async def positionen_vorschlaege_fuer_vorgang(
    session: AsyncSession, vorgang_id: UUID, mandant: Mandant
) -> list[RechnungPositionVorschlag]:
    """Fuer die "Vorschlaege aus Vorgang"-Box in RechnungDetailPage: fasst am
    Vorgang bereits erfasstes Material, abrechenbare Zeiterfassung UND
    Leistungsverzeichnis(LV)-Nutzung zu Positionsvorschlaegen zusammen, die
    der Nutzer gezielt uebernimmt (kein Automatismus -- siehe add_position,
    der weiterhin die einzige Stelle bleibt, die tatsaechlich eine Position
    anlegt). Zeiterfassung ohne lv_position_id hat nirgends einen
    hinterlegten Stundensatz, daher bleibt einzelpreis dort bewusst 0 -- der
    Nutzer traegt ihn beim Uebernehmen ein. Zeiterfassung MIT
    lv_position_id ist per SVS-Kopplung bereits bepreist (siehe
    ZeiterfassungManuellForm) und wird zusammen mit direkten
    LeistungsverzeichnisVerwendungen als eine "leistung"-Position je
    LV-Eintrag ausgegeben."""
    material_stmt = (
        select(
            Material.id,
            Material.bezeichnung,
            Material.einheit,
            Material.einzelpreis,
            func.sum(MaterialVerwendung.menge).label("menge"),
        )
        .join(Material, Material.id == MaterialVerwendung.material_id)
        .where(
            MaterialVerwendung.vorgang_id == vorgang_id,
            # Bereits in eine Rechnung uebernommenes Material ist gesperrt
            # (Spiegel zu Zeiterfassung.buchungsstatus == "gebucht").
            MaterialVerwendung.abrechnungsstatus == "offen",
        )
        .group_by(Material.id, Material.bezeichnung, Material.einheit, Material.einzelpreis)
        .order_by(Material.bezeichnung)
    )
    material_result = await session.execute(material_stmt)
    vorschlaege = [
        RechnungPositionVorschlag(
            quelle="material",
            beschreibung=bezeichnung,
            menge=menge,
            einheit=einheit,
            einzelpreis=einzelpreis or Decimal("0"),
            material_id=material_id,
        )
        for material_id, bezeichnung, einheit, einzelpreis, menge in material_result.all()
    ]

    # Zeit OHNE SVS-Kopplung: eine einzelne unbepreiste Sammelposition, wie
    # bisher -- der Nutzer traegt den Stundensatz manuell ein.
    zeit_ohne_lv_stmt = select(
        func.sum(func.extract("epoch", Zeiterfassung.ende_at - Zeiterfassung.start_at))
    ).where(
        Zeiterfassung.vorgang_id == vorgang_id,
        Zeiterfassung.kategorie == "auftrag",
        Zeiterfassung.abrechenbar.is_(True),
        Zeiterfassung.ende_at.is_not(None),
        Zeiterfassung.lv_position_id.is_(None),
        # Stufe 2 (docs/konzepte/ZEITERFASSUNG.md, Abschnitt 8): nur noch
        # aktiv gebuchte Zeit erscheint in Rechnungsvorschlaegen, vermerkte
        # und vorgemerkte Zeit nicht. Bereits abgerechnete Zeit ist ohnehin
        # keine offene Zeit mehr.
        Zeiterfassung.buchungsstatus == "gebucht",
        Zeiterfassung.geloescht_am.is_(None),
    )
    sekunden = (await session.execute(zeit_ohne_lv_stmt)).scalar_one_or_none()
    if sekunden:
        stunden = (Decimal(str(sekunden)) / _STUNDE).quantize(Decimal("0.01"))
        vorschlaege.append(
            RechnungPositionVorschlag(
                quelle="zeit",
                beschreibung="Arbeitszeit",
                menge=stunden,
                einheit="Std",
                einzelpreis=Decimal("0"),
            )
        )

    # Fahrzeit mit km (Stufe 4, docs/konzepte/ZEITERFASSUNG.md Abschnitt 8):
    # gesteuert ueber mandant.fahrzeit_abrechnung -- 'keine' zeigt wie bisher
    # nichts zusaetzlich. "Fahrzeit" (Stunden) bleibt exklusiv fuer
    # eigenstaendige Fahrt-Eintraege (kategorie="fahrzeit") -- Arbeitszeit
    # steckt immer schon in der "Zeit"-Position oben. "Fahrtkosten" (km)
    # summiert dagegen ueber BEIDE Kategorien (km kann seit Konzept
    # Abschnitt 11 auch an einer Arbeitszeit-Zeile haengen) und ist
    # unabhaengig vom Stunden-Anteil: eine Zeile, deren Stunden schon
    # abgerechnet sind, liefert ihr km weiter, solange es nicht selbst
    # gesperrt ist (km_abgerechnet_rechnung_id).
    if mandant.fahrzeit_abrechnung != "keine":
        fahrzeit_stunden_stmt = select(
            func.sum(func.extract("epoch", Zeiterfassung.ende_at - Zeiterfassung.start_at))
        ).where(
            Zeiterfassung.vorgang_id == vorgang_id,
            Zeiterfassung.kategorie == "fahrzeit",
            Zeiterfassung.abrechenbar.is_(True),
            Zeiterfassung.ende_at.is_not(None),
            Zeiterfassung.buchungsstatus == "gebucht",
            Zeiterfassung.geloescht_am.is_(None),
        )
        fahrzeit_sekunden = (await session.execute(fahrzeit_stunden_stmt)).scalar_one_or_none()
        if mandant.fahrzeit_abrechnung in ("zeit", "zeit_und_km") and fahrzeit_sekunden:
            vorschlaege.append(
                RechnungPositionVorschlag(
                    quelle="fahrzeit",
                    beschreibung="Fahrzeit",
                    menge=(Decimal(str(fahrzeit_sekunden)) / _STUNDE).quantize(Decimal("0.01")),
                    einheit="Std",
                    einzelpreis=mandant.fahrzeit_satz_netto or Decimal("0"),
                )
            )

        fahrtkosten_km_stmt = select(func.sum(Zeiterfassung.km)).where(
            Zeiterfassung.vorgang_id == vorgang_id,
            Zeiterfassung.kategorie.in_(("auftrag", "fahrzeit")),
            Zeiterfassung.km.is_not(None),
            Zeiterfassung.abrechenbar.is_(True),
            Zeiterfassung.ende_at.is_not(None),
            Zeiterfassung.buchungsstatus.in_(("gebucht", "abgerechnet")),
            km_frei_bedingung(),
            Zeiterfassung.geloescht_am.is_(None),
        )
        fahrtkosten_km = (await session.execute(fahrtkosten_km_stmt)).scalar_one_or_none()
        if mandant.fahrzeit_abrechnung in ("km", "zeit_und_km") and fahrtkosten_km:
            vorschlaege.append(
                RechnungPositionVorschlag(
                    quelle="fahrtkosten",
                    beschreibung="Fahrtkosten",
                    menge=Decimal(fahrtkosten_km).quantize(Decimal("0.1")),
                    einheit="km",
                    einzelpreis=mandant.km_satz_netto or Decimal("0"),
                )
            )

    # Leistungsverzeichnis: Zeit MIT SVS-Kopplung (nach lv_position_id
    # gruppiert und in Stunden umgerechnet) plus direkte
    # LeistungsverzeichnisVerwendungen -- beide Quellen sind bereits ueber
    # die LV-Position bepreist, daher je Position zu EINEM Vorschlag
    # zusammengefasst.
    zeit_je_lv_stmt = (
        select(
            Zeiterfassung.lv_position_id,
            func.sum(func.extract("epoch", Zeiterfassung.ende_at - Zeiterfassung.start_at)),
        )
        .where(
            Zeiterfassung.vorgang_id == vorgang_id,
            Zeiterfassung.kategorie == "auftrag",
            Zeiterfassung.abrechenbar.is_(True),
            Zeiterfassung.ende_at.is_not(None),
            Zeiterfassung.lv_position_id.is_not(None),
            Zeiterfassung.buchungsstatus == "gebucht",
            Zeiterfassung.geloescht_am.is_(None),
        )
        .group_by(Zeiterfassung.lv_position_id)
    )
    leistung_mengen: dict[UUID, Decimal] = defaultdict(Decimal)
    for lv_position_id, lv_sekunden in (await session.execute(zeit_je_lv_stmt)).all():
        leistung_mengen[lv_position_id] += (Decimal(str(lv_sekunden)) / _STUNDE).quantize(Decimal("0.01"))

    verwendung_stmt = (
        select(LeistungsverzeichnisVerwendung.lv_position_id, func.sum(LeistungsverzeichnisVerwendung.menge))
        .where(LeistungsverzeichnisVerwendung.vorgang_id == vorgang_id)
        .group_by(LeistungsverzeichnisVerwendung.lv_position_id)
    )
    for lv_position_id, menge in (await session.execute(verwendung_stmt)).all():
        leistung_mengen[lv_position_id] += menge

    if leistung_mengen:
        lv_positionen_result = await session.execute(
            select(LeistungsverzeichnisPosition).where(
                LeistungsverzeichnisPosition.id.in_(leistung_mengen.keys())
            )
        )
        for lv_position in sorted(lv_positionen_result.scalars().all(), key=lambda p: p.bezeichnung):
            vorschlaege.append(
                RechnungPositionVorschlag(
                    quelle="leistung",
                    beschreibung=lv_position.bezeichnung,
                    menge=leistung_mengen[lv_position.id].quantize(Decimal("0.01")),
                    einheit=lv_position.einheit,
                    einzelpreis=lv_position.einzelpreis,
                    lv_position_id=lv_position.id,
                )
            )

    return vorschlaege


def _quelle_bedingungen(quelle: str, lv_position_id: UUID | None) -> list | None:
    """Kategorie-/Kopplungs-Filter einer Quelle. "leistung" greift nur die
    SVS-gekoppelte Zeit (lv_position_id) und braucht deshalb den Parameter;
    "zeit" nur Zeilen ohne SVS-Kopplung (die gehoeren der "leistung").
    None fuer Quellen ohne Zeiterfassung ("material")."""
    if quelle == "leistung":
        if lv_position_id is None:
            return None
        return [Zeiterfassung.kategorie == "auftrag", Zeiterfassung.lv_position_id == lv_position_id]
    bedingungen = _zeiterfassung_quelle_filter(quelle)
    if bedingungen is not None and quelle == "zeit":
        bedingungen.append(Zeiterfassung.lv_position_id.is_(None))
    return bedingungen


async def _zeiterfassung_fuer_quelle(
    session: AsyncSession, vorgang_id: UUID, quelle: str, lv_position_id: UUID | None = None
) -> list[Zeiterfassung]:
    """Dieselben Kriterien wie in positionen_vorschlaege_fuer_vorgang, aber
    als tatsaechliche Zeilen statt Summe -- fuer das Sperren beim Uebernehmen
    einer Rechnungsposition (Konzept Abschnitt 8). Stunden-Quellen finden nur
    'gebucht'e Zeilen, "fahrtkosten" jede gebuchte/abgerechnete Zeile mit
    noch freiem km-Anteil."""
    bedingungen = _quelle_bedingungen(quelle, lv_position_id)
    if bedingungen is None:
        return []
    if quelle == "fahrtkosten":
        status_bedingung = [
            Zeiterfassung.buchungsstatus.in_(("gebucht", "abgerechnet")),
            km_frei_bedingung(),
        ]
    else:
        status_bedingung = [Zeiterfassung.buchungsstatus == "gebucht"]
    stmt = select(Zeiterfassung).where(
        Zeiterfassung.vorgang_id == vorgang_id,
        *bedingungen,
        Zeiterfassung.abrechenbar.is_(True),
        Zeiterfassung.ende_at.is_not(None),
        *status_bedingung,
        Zeiterfassung.geloescht_am.is_(None),
    )
    return list((await session.execute(stmt)).scalars().all())


def _protokoll(session: AsyncSession, eintrag: Zeiterfassung, aktion: str, geaendert_von: UUID | None) -> None:
    session.add(
        ZeiterfassungAenderung(
            mandant_id=eintrag.mandant_id,
            zeiterfassung_id=eintrag.id,
            aktion=aktion,
            geaendert_von=geaendert_von,
        )
    )


async def zeiterfassung_abrechnen(
    session: AsyncSession,
    *,
    vorgang_id: UUID,
    quelle: str,
    rechnung_id: UUID,
    geaendert_von: UUID,
    lv_position_id: UUID | None = None,
) -> None:
    """Sperrt die einer "zeit"/"fahrzeit"/"fahrtkosten"/"leistung"-Position
    zugrunde liegenden Zeiterfassung-Eintraege (Konzept Abschnitt 8/9:
    gebucht+abgerechnet sind Rechnungsgrundlage und daher GoBD-gesperrt).
    Stunden-Quellen setzen nur buchungsstatus/abgerechnet_rechnung_id,
    "fahrtkosten" nur km_abgerechnet_rechnung_id -- die Anteile einer Zeile
    sind unabhaengig voneinander."""
    for eintrag in await _zeiterfassung_fuer_quelle(session, vorgang_id, quelle, lv_position_id):
        if quelle == "fahrtkosten":
            eintrag.km_abgerechnet_rechnung_id = rechnung_id
            _protokoll(session, eintrag, "km_abgerechnet", geaendert_von)
        else:
            eintrag.buchungsstatus = "abgerechnet"
            eintrag.abgerechnet_rechnung_id = rechnung_id
            _protokoll(session, eintrag, "abgerechnet", geaendert_von)


async def zeiterfassung_abrechnung_zuruecksetzen(
    session: AsyncSession,
    *,
    rechnung_id: UUID,
    quelle: str,
    vorgang_id: UUID,
    geaendert_von: UUID,
    lv_position_id: UUID | None = None,
) -> None:
    """Kehrt zeiterfassung_abrechnen beim Entfernen einer Rechnungsposition
    um -- nur der Anteil dieser Quelle wird frei. Der Aufrufer (remove_position
    in app/api/routes/rechnungen.py) ruft nicht auf, solange noch eine
    Position derselben Quelle auf derselben Rechnung dieselben Zeilen
    braucht."""
    bedingungen = _quelle_bedingungen(quelle, lv_position_id)
    if bedingungen is None:
        return
    if quelle == "fahrtkosten":
        verweis_bedingung = Zeiterfassung.km_abgerechnet_rechnung_id == rechnung_id
    else:
        verweis_bedingung = (Zeiterfassung.abgerechnet_rechnung_id == rechnung_id) & (
            Zeiterfassung.buchungsstatus == "abgerechnet"
        )
    stmt = select(Zeiterfassung).where(verweis_bedingung, Zeiterfassung.vorgang_id == vorgang_id, *bedingungen)
    for eintrag in (await session.execute(stmt)).scalars().all():
        if quelle == "fahrtkosten":
            eintrag.km_abgerechnet_rechnung_id = None
            _protokoll(session, eintrag, "km_abrechnung_zurueckgesetzt", geaendert_von)
        else:
            eintrag.buchungsstatus = "gebucht"
            eintrag.abgerechnet_rechnung_id = None
            _protokoll(session, eintrag, "abrechnung_zurueckgesetzt", geaendert_von)


async def zeiterfassung_freigeben_fuer_rechnung(
    session: AsyncSession, *, rechnung_id: UUID, geaendert_von: UUID | None, verweis_behalten: bool
) -> None:
    """Gibt alle von dieser Rechnung gesperrten Anteile frei, Stunden wie km
    (Loeschen des Entwurfs, Storno). verweis_behalten=True laesst die
    Verweise stehen, damit ein Wiederherstellen aus dem Papierkorb genau
    diese Zeilen wieder sperren kann (zeiterfassung_wieder_sperren_fuer_
    rechnung). Beim Stunden-Anteil geschieht das ueber buchungsstatus
    'gebucht' + Verweis, beim km-Anteil gilt der Verweis auf einen Entwurf im
    Papierkorb von selbst als frei (km_frei_bedingung) -- dort wird nur
    protokolliert."""
    stmt = select(Zeiterfassung).where(
        Zeiterfassung.abgerechnet_rechnung_id == rechnung_id,
        Zeiterfassung.buchungsstatus == "abgerechnet",
    )
    for eintrag in (await session.execute(stmt)).scalars().all():
        eintrag.buchungsstatus = "gebucht"
        if not verweis_behalten:
            eintrag.abgerechnet_rechnung_id = None
        _protokoll(session, eintrag, "abrechnung_zurueckgesetzt", geaendert_von)

    km_stmt = select(Zeiterfassung).where(Zeiterfassung.km_abgerechnet_rechnung_id == rechnung_id)
    for eintrag in (await session.execute(km_stmt)).scalars().all():
        if not verweis_behalten:
            eintrag.km_abgerechnet_rechnung_id = None
        _protokoll(session, eintrag, "km_abrechnung_zurueckgesetzt", geaendert_von)


async def zeiterfassung_wieder_sperren_fuer_rechnung(
    session: AsyncSession, *, rechnung_id: UUID, geaendert_von: UUID | None
) -> None:
    """Gegenstueck zu zeiterfassung_freigeben_fuer_rechnung(verweis_behalten=
    True) beim Wiederherstellen aus dem Papierkorb. Zeilen, die zwischenzeitlich
    von einer anderen Rechnung gesperrt wurden, zeigen auf diese und werden
    von der Verweis-Bedingung uebergangen; Zeilen mit geleertem Verweis
    bleiben frei. Der km-Anteil ist mit dem Wiederherstellen der Rechnung
    (geloescht_am=NULL) bereits wieder gesperrt -- nur das Protokoll fehlt."""
    stmt = select(Zeiterfassung).where(
        Zeiterfassung.abgerechnet_rechnung_id == rechnung_id,
        Zeiterfassung.buchungsstatus == "gebucht",
        Zeiterfassung.geloescht_am.is_(None),
    )
    for eintrag in (await session.execute(stmt)).scalars().all():
        eintrag.buchungsstatus = "abgerechnet"
        _protokoll(session, eintrag, "abgerechnet", geaendert_von)

    km_stmt = select(Zeiterfassung).where(
        Zeiterfassung.km_abgerechnet_rechnung_id == rechnung_id,
        Zeiterfassung.geloescht_am.is_(None),
    )
    for eintrag in (await session.execute(km_stmt)).scalars().all():
        _protokoll(session, eintrag, "km_abgerechnet", geaendert_von)


async def zeiterfassung_verweis_loesen(session: AsyncSession, *, rechnung_id: UUID) -> None:
    """Vor dem endgueltigen Loeschen einer Rechnung: der behaltene Verweis
    auf freigegebene Anteile ('gebucht'e Stunden, km) wuerde sonst am FK
    scheitern bzw. (km: ON DELETE SET NULL) nur implizit geloest."""
    await session.execute(
        update(Zeiterfassung)
        .where(
            Zeiterfassung.abgerechnet_rechnung_id == rechnung_id,
            Zeiterfassung.buchungsstatus == "gebucht",
        )
        .values(abgerechnet_rechnung_id=None)
    )
    await session.execute(
        update(Zeiterfassung)
        .where(Zeiterfassung.km_abgerechnet_rechnung_id == rechnung_id)
        .values(km_abgerechnet_rechnung_id=None)
    )


async def material_abrechnen(
    session: AsyncSession, *, vorgang_id: UUID, material_id: UUID, rechnung_id: UUID
) -> None:
    """Sperrt alle offenen Verwendungen dieses Materials am Vorgang, wenn die
    zugehoerige "material"-Position in eine Rechnung uebernommen wird
    (Spiegel zu zeiterfassung_abrechnen). Bestand/Bewegungen bleiben
    unberuehrt -- die wurden schon beim Erfassen der Verwendung gebucht."""
    stmt = select(MaterialVerwendung).where(
        MaterialVerwendung.vorgang_id == vorgang_id,
        MaterialVerwendung.material_id == material_id,
        MaterialVerwendung.abrechnungsstatus == "offen",
    )
    for verwendung in (await session.execute(stmt)).scalars().all():
        verwendung.abrechnungsstatus = "abgerechnet"
        verwendung.abgerechnet_rechnung_id = rechnung_id


async def material_abrechnung_zuruecksetzen(
    session: AsyncSession, *, rechnung_id: UUID, vorgang_id: UUID, material_id: UUID
) -> None:
    """Kehrt material_abrechnen beim Entfernen einer Material-Position um. Der
    Aufrufer prueft vorher, ob noch eine zweite Position mit gleichem
    Vorgang+Material auf der Rechnung besteht."""
    stmt = select(MaterialVerwendung).where(
        MaterialVerwendung.abgerechnet_rechnung_id == rechnung_id,
        MaterialVerwendung.abrechnungsstatus == "abgerechnet",
        MaterialVerwendung.vorgang_id == vorgang_id,
        MaterialVerwendung.material_id == material_id,
    )
    for verwendung in (await session.execute(stmt)).scalars().all():
        verwendung.abrechnungsstatus = "offen"
        verwendung.abgerechnet_rechnung_id = None


async def material_freigeben_fuer_rechnung(
    session: AsyncSession, *, rechnung_id: UUID, verweis_behalten: bool
) -> None:
    """Gegenstueck zu zeiterfassung_freigeben_fuer_rechnung fuer Material
    (Loeschen des Entwurfs, Storno). verweis_behalten=True laesst den Verweis
    fuers Wiederherstellen aus dem Papierkorb stehen."""
    stmt = select(MaterialVerwendung).where(
        MaterialVerwendung.abgerechnet_rechnung_id == rechnung_id,
        MaterialVerwendung.abrechnungsstatus == "abgerechnet",
    )
    for verwendung in (await session.execute(stmt)).scalars().all():
        verwendung.abrechnungsstatus = "offen"
        if not verweis_behalten:
            verwendung.abgerechnet_rechnung_id = None


async def material_wieder_sperren_fuer_rechnung(session: AsyncSession, *, rechnung_id: UUID) -> None:
    """Gegenstueck zu material_freigeben_fuer_rechnung(verweis_behalten=True)
    beim Wiederherstellen. Verwendungen, die zwischenzeitlich von einer
    anderen Rechnung gesperrt wurden, zeigen auf diese und werden uebergangen."""
    stmt = select(MaterialVerwendung).where(
        MaterialVerwendung.abgerechnet_rechnung_id == rechnung_id,
        MaterialVerwendung.abrechnungsstatus == "offen",
    )
    for verwendung in (await session.execute(stmt)).scalars().all():
        verwendung.abrechnungsstatus = "abgerechnet"


async def material_verweis_loesen(session: AsyncSession, *, rechnung_id: UUID) -> None:
    """Vor dem endgueltigen Loeschen einer Rechnung: siehe
    zeiterfassung_verweis_loesen."""
    await session.execute(
        update(MaterialVerwendung)
        .where(
            MaterialVerwendung.abgerechnet_rechnung_id == rechnung_id,
            MaterialVerwendung.abrechnungsstatus == "offen",
        )
        .values(abgerechnet_rechnung_id=None)
    )


def _auswahl_schluessel(
    quelle: str, lv_position_id: UUID | None, material_id: UUID | None
) -> tuple[str, UUID | None, UUID | None]:
    """Identifiziert einen Vorschlag-Posten: die IDs zaehlen nur bei der
    Quelle, zu der sie gehoeren."""
    return (
        quelle,
        lv_position_id if quelle == "leistung" else None,
        material_id if quelle == "material" else None,
    )


async def vorgang_uebernehmen(
    session: AsyncSession,
    *,
    rechnung: Rechnung,
    vorgang: Vorgang,
    mandant: Mandant,
    stundensatz: Decimal,
    auswahl: list[RechnungVorgangAuswahlPosten],
    actor_user_id: UUID,
) -> int:
    """Uebernimmt die gewaehlten Posten eines Vorgangs in den Rechnungsentwurf
    und sperrt deren Grundlage (Zeit/Leistung/Material). Die Vorschlaege
    werden neu berechnet -- was seit der Auswahl nicht mehr offen ist, wird
    uebersprungen statt abzubrechen. Gibt die Anzahl angelegter Positionen
    zurueck."""
    gewaehlt = {_auswahl_schluessel(a.quelle, a.lv_position_id, a.material_id) for a in auswahl}
    vorschlaege = await positionen_vorschlaege_fuer_vorgang(session, vorgang.id, mandant)
    naechste_position = max((p.position for p in await positionen_fuer(session, rechnung.id)), default=0) + 1
    kleinunternehmer = steuer_service.ist_kleinunternehmer(mandant)
    steuer_kategorie, steuer_satz = steuer_service.beleg_vorbelegung(
        rechnung.mwst_satz, kleinunternehmer=kleinunternehmer
    )
    steuer_grund = "kleinunternehmer_19" if kleinunternehmer else None

    angelegt = 0
    for vorschlag in vorschlaege:
        if _auswahl_schluessel(vorschlag.quelle, vorschlag.lv_position_id, vorschlag.material_id) not in gewaehlt:
            continue
        session.add(
            RechnungPosition(
                mandant_id=rechnung.mandant_id,
                rechnung_id=rechnung.id,
                position=naechste_position,
                # Ohne Vorgangsnummer: der Gruppenkopf zeigt den Vorgang.
                beschreibung=vorschlag.beschreibung,
                menge=vorschlag.menge,
                einheit=vorschlag.einheit,
                einzelpreis=stundensatz if vorschlag.quelle == "zeit" else vorschlag.einzelpreis,
                steuer_kategorie=steuer_kategorie,
                steuer_satz=steuer_satz,
                steuer_grund=steuer_grund,
                quelle=vorschlag.quelle,
                vorgang_id=vorgang.id,
                lv_position_id=vorschlag.lv_position_id,
                material_id=vorschlag.material_id,
            )
        )
        naechste_position += 1
        angelegt += 1
        if vorschlag.quelle == "material":
            if vorschlag.material_id is not None:
                await material_abrechnen(
                    session, vorgang_id=vorgang.id, material_id=vorschlag.material_id, rechnung_id=rechnung.id
                )
        else:
            await zeiterfassung_abrechnen(
                session,
                vorgang_id=vorgang.id,
                quelle=vorschlag.quelle,
                rechnung_id=rechnung.id,
                geaendert_von=actor_user_id,
                lv_position_id=vorschlag.lv_position_id,
            )

    if angelegt:
        session.add(
            VorgangEvent(
                mandant_id=rechnung.mandant_id,
                vorgang_id=vorgang.id,
                event_type="rechnung_status",
                author_user_id=actor_user_id,
                body=f"Rechnung {rechnung.rechnungsnummer}: Vorgang übernommen",
                payload={"rechnung_id": str(rechnung.id), "status": rechnung.status},
            )
        )
    await session.flush()
    return angelegt


def netto_betrag(rechnung: Rechnung, positionen: list[RechnungPosition]) -> Decimal:
    """Positionen (falls vorhanden) sind die Quelle der Wahrheit, dieselbe
    Ueberlegung wie bei Angebot.gesamt_netto: verhindert eine veraltete Summe
    nach nachtraeglicher Preisaenderung einer Position. Ohne Positionen (der
    einfache Fall aus Phase 6, eine Abschlussrechnung ohne eigene Zeilen)
    bleibt der manuell gesetzte betrag_netto massgeblich. Die Regel lebt in
    steuer_service."""
    return steuer_service.netto_summe(steuer_service.steuer_gruppen(rechnung, positionen))


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
    return steuer_service.brutto_summe(steuer_service.steuer_gruppen(rechnung, positionen))


def status_nach_zahlung(
    brutto: Decimal, bezahlt: Decimal, aktueller_status: str, gutschriften: Decimal = Decimal("0")
) -> str:
    """Die einzige Stelle, die entscheidet, ob eine Rechnung nach einer
    Zahlungsbuchung versendet/teilweise_bezahlt/bezahlt ist -- Zahlungen
    fuehren den Status, nicht der Nutzer. entwurf/storniert werden hier nie
    hereingegeben (siehe Aufrufer-Gates in den Routen). gutschriften ist die
    Summe der Brutto-Betraege (positiv) der nicht stornierten Gutschriften:
    sie decken den Betrag wie eine Zahlung, machen die Rechnung aber nicht
    zu "teilweise_bezahlt" (dafuer zaehlen nur echte Zahlungen)."""
    offen = brutto - bezahlt - gutschriften
    if offen <= 0:
        return "bezahlt"
    if bezahlt > 0:
        return "teilweise_bezahlt"
    return aktueller_status


def netto_sql(beleg=Rechnung):
    """Netto als SQL-Ausdruck -- Gegenstueck zu netto_betrag() fuer alles, was
    in der Datenbank gefiltert, sortiert oder summiert werden muss (Betrags-
    filter und Summenzeile der Rechnungsuebersicht)."""
    return steuer_service.netto_sql(beleg)


def brutto_sql(beleg=Rechnung):
    """Brutto als SQL-Ausdruck. Brutto ist absichtlich nirgends persistiert
    (siehe RechnungRead.betrag_brutto) -- fuers Filtern/Sortieren nach Betrag
    braucht es die Formel trotzdem in SQL, statt eine redundante Spalte
    einzufuehren, die gegen brutto_betrag() auseinanderlaufen koennte."""
    return steuer_service.brutto_sql(beleg)


def bezahlt_sql(beleg=Rechnung):
    """Summe der Zahlungen als SQL-Ausdruck -- Gegenstueck zu
    RechnungRead.bezahlter_betrag. Negative Gegenbuchungen (Zahlungs-Storno)
    rechnen sich hier arithmetisch von selbst heraus."""
    zahlung = RechnungZahlung if beleg is Rechnung else aliased(RechnungZahlung)
    zahlungen_summe = (
        select(func.sum(zahlung.betrag)).where(zahlung.rechnung_id == beleg.id).correlate(beleg).scalar_subquery()
    )
    return func.coalesce(zahlungen_summe, Decimal("0"))


# --- Offene Posten mit Gutschriften ------------------------------------------
#
# EINE Regel, hier in Python (offener_betrag_regel, guthaben_regel) und als SQL
# (offen_sql); test_rechnungsarten.py vergleicht beide auf mehreren Faellen.
#
# - Normale Rechnung: offen = Brutto - Zahlungen - Summe |Brutto| der nicht
#   stornierten Gutschriften, mindestens 0.
# - Gegenbeleg (Gutschrift bzw. Storno-Beleg mit negativem Brutto): offen ist 0
#   oder, wenn er mehr zuruecknimmt als an der Bezugsrechnung noch offen war,
#   der Ueberhang als Guthaben (negativ). Bei mehreren Gutschriften zu einer
#   Rechnung nehmen die frueheren (created_at, id) den offenen Rest zuerst auf.
#   Ein Storno-Beleg verhaelt sich wie eine Gutschrift ueber den ganzen Betrag:
#   sein Guthaben ist, was auf die stornierte Rechnung schon gezahlt war.
# - Ein Storno-Beleg einer Gutschrift hat positives Brutto und gilt als normale
#   Forderung.

_NULL = Decimal("0")


def ist_gegenbeleg(rechnung: Rechnung, brutto: Decimal) -> bool:
    return brutto < 0 and (rechnung.bezug_rechnung_id is not None or rechnung.storniert_rechnung_id is not None)


def offener_betrag_regel(brutto: Decimal, bezahlt: Decimal, gutschriften_abs: Decimal) -> Decimal:
    return max(brutto - bezahlt - gutschriften_abs, _NULL).quantize(_CENT)


def guthaben_regel(gutschrift_abs: Decimal, vorher_abs: Decimal, rest_bezug: Decimal) -> Decimal:
    """Ueberhang (>= 0) einer Gutschrift ueber den offenen Rest der Bezugs-
    rechnung hinaus; vorher_abs sind die Gutschriften davor, rest_bezug
    max(Brutto - Zahlungen, 0) der Bezugsrechnung."""
    return min(gutschrift_abs, max(vorher_abs + gutschrift_abs - rest_bezug, _NULL)).quantize(_CENT)


def gutschrift_summe_sql(beleg=Rechnung):
    gutschrift = aliased(Rechnung)
    summe = (
        select(func.sum(func.abs(brutto_sql(gutschrift))))
        .where(
            gutschrift.bezug_rechnung_id == beleg.id,
            gutschrift.rechnungsart == "gutschrift",
            gutschrift.status != "storniert",
            gutschrift.geloescht_am.is_(None),
        )
        .correlate(beleg)
        .scalar_subquery()
    )
    return func.coalesce(summe, _NULL)


def guthaben_sql(beleg=Rechnung):
    """SQL-Gegenstueck zu guthaben_regel fuer einen Gegenbeleg."""
    bezug = aliased(Rechnung)
    vorher = aliased(Rechnung)
    betrag = func.abs(brutto_sql(beleg))
    rest_bezug = (
        select(func.greatest(brutto_sql(bezug) - bezahlt_sql(bezug), _NULL))
        .where(bezug.id == func.coalesce(beleg.bezug_rechnung_id, beleg.storniert_rechnung_id))
        .correlate(beleg)
        .scalar_subquery()
    )
    vorher_summe = (
        select(func.sum(func.abs(brutto_sql(vorher))))
        .where(
            vorher.bezug_rechnung_id == beleg.bezug_rechnung_id,
            vorher.rechnungsart == "gutschrift",
            vorher.status != "storniert",
            vorher.geloescht_am.is_(None),
            tuple_(vorher.created_at, vorher.id) < tuple_(beleg.created_at, beleg.id),
        )
        .correlate(beleg)
        .scalar_subquery()
    )
    return func.least(
        betrag,
        func.greatest(func.coalesce(vorher_summe, _NULL) + betrag - func.coalesce(rest_bezug, _NULL), _NULL),
    )


def offen_sql(beleg=Rechnung):
    """Offener Betrag als SQL-Ausdruck, die Regel steht oben. Reicht NICHT,
    einfach den vollen Bruttobetrag zu nehmen, sobald es teilweise_bezahlt
    oder Gutschriften gibt -- sonst zaehlt eine zu 90% bezahlte Rechnung als
    voll offen."""
    brutto = brutto_sql(beleg)
    normal = func.greatest(brutto - bezahlt_sql(beleg) - gutschrift_summe_sql(beleg), _NULL)
    gegenbeleg = and_(
        brutto < 0, or_(beleg.bezug_rechnung_id.is_not(None), beleg.storniert_rechnung_id.is_not(None))
    )
    return case((gegenbeleg, -guthaben_sql(beleg)), else_=normal)


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
    "vorgaenge",
    "angerechnete_abschlaege",
    "gutschriften",
    "betrag_netto",
    "betrag_steuer",
    "steuergruppen",
    "betrag_brutto",
    "bezahlter_betrag",
    "offener_betrag",
    "ist_ueberfaellig",
    "tage_ueberfaellig",
)


async def vorgang_koepfe_fuer_mehrere(
    session: AsyncSession, rechnung_ids: list[UUID]
) -> dict[UUID, list[RechnungVorgangKopf]]:
    """Eine Query fuer alle Rechnungen einer Seite: distinct Vorgaenge der
    Positionen, je Rechnung nach der ersten Positionsnummer sortiert."""
    if not rechnung_ids:
        return {}
    erste_position = func.min(RechnungPosition.position)
    result = await session.execute(
        select(RechnungPosition.rechnung_id, Vorgang.id, Vorgang.vorgangsnummer, Vorgang.titel)
        .join(Vorgang, Vorgang.id == RechnungPosition.vorgang_id)
        .where(RechnungPosition.rechnung_id.in_(rechnung_ids))
        .group_by(RechnungPosition.rechnung_id, Vorgang.id, Vorgang.vorgangsnummer, Vorgang.titel)
        .order_by(RechnungPosition.rechnung_id, erste_position)
    )
    gruppiert: dict[UUID, list[RechnungVorgangKopf]] = {rid: [] for rid in rechnung_ids}
    for rechnung_id, vorgang_id, nummer, titel in result.all():
        gruppiert[rechnung_id].append(RechnungVorgangKopf(id=vorgang_id, vorgangsnummer=nummer, titel=titel))
    return gruppiert


async def vorgang_koepfe_map(
    session: AsyncSession, positionen: list[RechnungPosition]
) -> dict[UUID, tuple[str, str]]:
    """vorgang_id -> (Vorgangsnummer, Titel) fuer die Gruppenkoepfe der PDF."""
    ids = {p.vorgang_id for p in positionen if p.vorgang_id is not None}
    if not ids:
        return {}
    result = await session.execute(
        select(Vorgang.id, Vorgang.vorgangsnummer, Vorgang.titel).where(Vorgang.id.in_(ids))
    )
    return {vorgang_id: (nummer, titel) for vorgang_id, nummer, titel in result.all()}


@dataclass
class BelegKontext:
    """Was ein Beleg ueber sich hinaus fuer das Lesemodell braucht: den
    offenen Betrag nach der zentralen Regel, die Gutschriften am Original, die
    angerechneten Abschlaege und je Position die schon gutgeschriebene Menge."""

    offener_betrag: Decimal = _NULL
    gutschriften: list[GutschriftKurzRead] = field(default_factory=list)
    angerechnete_abschlaege: list[AngerechneterAbschlagRead] = field(default_factory=list)
    gutgeschrieben: dict[UUID, Decimal] = field(default_factory=dict)


def _gutschrift_reihenfolge(r: Rechnung) -> tuple:
    return (r.created_at, r.id)


async def beleg_kontexte(
    session: AsyncSession,
    rechnungen: list[Rechnung],
    positionen_je: dict[UUID, list[RechnungPosition]],
    zahlungen_je: dict[UUID, list[RechnungZahlung]],
) -> dict[UUID, BelegKontext]:
    """Bulk-Berechnung der BelegKontexte einer Seite (eine Handvoll Queries
    statt eine je Zeile). Die Python-Seite der Offene-Posten-Regel."""
    if not rechnungen:
        return {}
    brutto_je = {
        r.id: brutto_betrag(r, positionen_je.get(r.id, [])) for r in rechnungen
    }
    gegenbelege = [r for r in rechnungen if ist_gegenbeleg(r, brutto_je[r.id])]
    bezug_ids = {r.bezug_rechnung_id or r.storniert_rechnung_id for r in gegenbelege}

    bezuege: dict[UUID, Rechnung] = {r.id: r for r in rechnungen if r.id in bezug_ids}
    fehlende = bezug_ids - bezuege.keys()
    if fehlende:
        for bezug in (await session.execute(select(Rechnung).where(Rechnung.id.in_(fehlende)))).scalars().all():
            bezuege[bezug.id] = bezug
    bezug_positionen = dict(positionen_je)
    bezug_zahlungen = dict(zahlungen_je)
    fehlende_daten = [i for i in bezuege if i not in bezug_positionen]
    if fehlende_daten:
        bezug_positionen.update(await positionen_fuer_mehrere(session, fehlende_daten))
        bezug_zahlungen.update(await zahlungen_fuer_mehrere(session, fehlende_daten))

    # Nicht stornierte Gutschriften zu allen betroffenen Originalen: den
    # Belegen der Seite und den Bezugsrechnungen der Gegenbelege.
    original_ids = {r.id for r in rechnungen} | set(bezuege)
    gutschriften_je: dict[UUID, list[Rechnung]] = defaultdict(list)
    gutschrift_zeilen = (
        await session.execute(
            select(Rechnung)
            .where(
                Rechnung.bezug_rechnung_id.in_(original_ids),
                Rechnung.rechnungsart == "gutschrift",
                Rechnung.status != "storniert",
                Rechnung.geloescht_am.is_(None),
            )
            .order_by(Rechnung.created_at, Rechnung.id)
        )
    ).scalars().all()
    for g in gutschrift_zeilen:
        gutschriften_je[g.bezug_rechnung_id].append(g)
    gutschrift_positionen = (
        await positionen_fuer_mehrere(session, [g.id for g in gutschrift_zeilen]) if gutschrift_zeilen else {}
    )
    gutschrift_brutto = {
        g.id: brutto_betrag(g, gutschrift_positionen.get(g.id, [])) for g in gutschrift_zeilen
    }

    abschlag_ids = {
        p.abschlag_rechnung_id
        for r in rechnungen
        for p in positionen_je.get(r.id, [])
        if p.abschlag_rechnung_id is not None
    }
    abschlaege: dict[UUID, Rechnung] = {}
    if abschlag_ids:
        abschlaege = {
            a.id: a
            for a in (await session.execute(select(Rechnung).where(Rechnung.id.in_(abschlag_ids)))).scalars().all()
        }

    kontexte: dict[UUID, BelegKontext] = {}
    for r in rechnungen:
        brutto = brutto_je[r.id]
        bezahlt = bezahlter_betrag(zahlungen_je.get(r.id, []))
        kontext = BelegKontext()
        eigene_gutschriften = gutschriften_je.get(r.id, [])
        kontext.gutschriften = [
            GutschriftKurzRead(rechnung_id=g.id, rechnungsnummer=g.rechnungsnummer, brutto=gutschrift_brutto[g.id])
            for g in eigene_gutschriften
        ]
        for g in eigene_gutschriften:
            for p in gutschrift_positionen.get(g.id, []):
                if p.bezug_position_id is not None:
                    kontext.gutgeschrieben[p.bezug_position_id] = (
                        kontext.gutgeschrieben.get(p.bezug_position_id, _NULL) + p.menge
                    )
        if ist_gegenbeleg(r, brutto):
            bezug = bezuege.get(r.bezug_rechnung_id or r.storniert_rechnung_id)
            rest = _NULL
            vorher = _NULL
            if bezug is not None:
                rest = max(
                    brutto_betrag(bezug, bezug_positionen.get(bezug.id, []))
                    - bezahlter_betrag(bezug_zahlungen.get(bezug.id, [])),
                    _NULL,
                )
                if r.bezug_rechnung_id is not None:
                    vorher = sum(
                        (
                            abs(gutschrift_brutto[g.id])
                            for g in gutschriften_je.get(bezug.id, [])
                            if _gutschrift_reihenfolge(g) < _gutschrift_reihenfolge(r)
                        ),
                        _NULL,
                    )
            guthaben = guthaben_regel(abs(brutto), vorher, rest)
            kontext.offener_betrag = -guthaben if guthaben else guthaben.copy_abs()
        else:
            kontext.offener_betrag = offener_betrag_regel(
                brutto, bezahlt, sum((abs(gutschrift_brutto[g.id]) for g in eigene_gutschriften), _NULL)
            )
        for p in positionen_je.get(r.id, []):
            if p.abschlag_rechnung_id is not None and p.abschlag_rechnung_id in abschlaege:
                a = abschlaege[p.abschlag_rechnung_id]
                kontext.angerechnete_abschlaege.append(
                    AngerechneterAbschlagRead(
                        rechnung_id=a.id,
                        rechnungsnummer=a.rechnungsnummer,
                        datum=a.created_at.date(),
                        netto=-steuer_service.runde_cent(p.menge * p.einzelpreis),
                    )
                )
        kontexte[r.id] = kontext
    return kontexte


async def offene_betraege(session: AsyncSession, rechnungen: list[Rechnung]) -> dict[UUID, Decimal]:
    """Offener Betrag je Rechnung nach der zentralen Regel -- fuer Insights und
    Mahnwesen, die nicht ueber die SQL-Seite (offen_sql) laufen."""
    ids = [r.id for r in rechnungen]
    kontexte = await beleg_kontexte(
        session, rechnungen, await positionen_fuer_mehrere(session, ids), await zahlungen_fuer_mehrere(session, ids)
    )
    return {rid: k.offener_betrag for rid, k in kontexte.items()}


def _read_model_aus(
    rechnung: Rechnung,
    positionen: list[RechnungPosition],
    zahlungen: list[RechnungZahlung],
    vorgaenge: list[RechnungVorgangKopf],
    kontext: BelegKontext,
) -> RechnungRead:
    gruppen = steuer_service.steuer_gruppen(rechnung, positionen)
    positionen_read = []
    for p in positionen:
        gelesen = RechnungPositionRead.model_validate(p)
        gelesen.bereits_gutgeschrieben = kontext.gutgeschrieben.get(p.id, _NULL).quantize(_CENT)
        positionen_read.append(gelesen)
    return RechnungRead(
        **{k: getattr(rechnung, k) for k in RechnungRead.model_fields if k not in _AUSGESCHLOSSENE_FELDER},
        betrag_netto=steuer_service.netto_summe(gruppen),
        betrag_steuer=steuer_service.steuer_summe(gruppen),
        steuergruppen=[RechnungSteuerGruppeRead.model_validate(g) for g in gruppen],
        positionen=positionen_read,
        zahlungen=[RechnungZahlungRead.model_validate(z) for z in zahlungen],
        vorgaenge=vorgaenge,
        offener_betrag=kontext.offener_betrag,
        gutschriften=kontext.gutschriften,
        angerechnete_abschlaege=kontext.angerechnete_abschlaege,
    )


async def to_read_model_bulk(
    session: AsyncSession, rechnungen: list[Rechnung]
) -> list[RechnungRead]:
    ids = [r.id for r in rechnungen]
    positionen_je_rechnung = await positionen_fuer_mehrere(session, ids)
    zahlungen_je_rechnung = await zahlungen_fuer_mehrere(session, ids)
    vorgaenge_je_rechnung = await vorgang_koepfe_fuer_mehrere(session, ids)
    kontexte = await beleg_kontexte(session, rechnungen, positionen_je_rechnung, zahlungen_je_rechnung)
    return [
        _read_model_aus(
            r,
            positionen_je_rechnung.get(r.id, []),
            zahlungen_je_rechnung.get(r.id, []),
            vorgaenge_je_rechnung.get(r.id, []),
            kontexte[r.id],
        )
        for r in rechnungen
    ]


async def to_read_model(session: AsyncSession, rechnung: Rechnung) -> RechnungRead:
    return (await to_read_model_bulk(session, [rechnung]))[0]


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
                steuer_kategorie=p.steuer_kategorie,
                steuer_satz=p.steuer_satz,
                steuer_grund=p.steuer_grund,
                steuer_grund_text=p.steuer_grund_text,
                # Nur fuer die Gruppendarstellung der Storno-PDF -- quelle/
                # lv_position_id/material_id bleiben leer, damit der Beleg nie
                # als Sperrgrundlage gilt.
                vorgang_id=p.vorgang_id,
            )
        )

    original.status = "storniert"
    await session.flush()
    await session.refresh(storno)
    return storno


class VersandFehler(Exception):
    """Versand/Archivierung ist nicht moeglich; die Meldung geht als 422 an den
    Aufrufer (routes/rechnungen.py)."""


def versand_meldung(probleme: list[str]) -> str:
    return "Rechnung kann nicht versendet werden:\n" + "\n".join(f"- {p}" for p in probleme)


def pruefe_versand(mandant: Mandant, rechnung: Rechnung, kunde: Kunde, positionen: list[RechnungPosition]) -> list[str]:
    """Alle Pflichtangaben vor dem Versand: Steuergruende/13b-Voraussetzungen
    (nur Nicht-Kleinunternehmer) und, wenn der E-Rechnung-Modus des Mandanten fuer
    diesen Kunden greift, die EN16931-Pflichtfelder (beim Profil XRechnung samt
    BR-DE-Zusatzangaben). Leere Liste = versendbar."""
    probleme = steuer_service.pruefe_steuer_fuer_versand(mandant, rechnung, kunde, positionen)
    if e_invoice_service.e_rechnung_gilt(mandant, kunde):
        probleme += e_invoice_service.pruefe_e_rechnung(mandant, rechnung, kunde, positionen)
    return list(dict.fromkeys(probleme))


def _kurzgrund_e_rechnung(exc: Exception) -> str:
    # Die Details (lxml-Fehlerliste mit Elementpfaden) gehoeren ins Log, nicht
    # in die Antwort.
    if isinstance(exc, etree.LxmlError):
        return "Schema-Validierung fehlgeschlagen"
    return "unerwarteter Fehler beim Aufbau der XML"


def _rechnung_dokument_bytes(
    rechnung: Rechnung,
    mandant: Mandant,
    kunde: Kunde,
    positionen: list[RechnungPosition],
    storniert_rechnung: Rechnung | None,
    vorgang_koepfe: dict[UUID, tuple[str, str]],
    logo_bytes: bytes | None = None,
    *,
    strikt: bool = True,
    bezug_rechnung: Rechnung | None = None,
    angerechnete_abschlaege: list[Rechnung] | None = None,
) -> tuple[bytes, bytes | None, str | None]:
    """(PDF, XML, Profil). Normales PDF ist immer der Ausgangspunkt. Greift der
    E-Rechnung-Modus des Mandanten fuer den Kunden, entsteht stattdessen ein Hybrid-PDF
    (mit eingebetteter CII-XML); beim Profil XRechnung gilt die XML als die Rechnung,
    das PDF ist deren eingebettete Lesefassung. Die XML wird in beiden Faellen
    zusaetzlich einzeln archiviert. strikt (Versand): fehlende Pflichtangaben oder ein Fehler beim
    Erzeugen brechen mit VersandFehler ab statt still aufs normale PDF
    zurueckzufallen. Nicht strikt (Storno): ein bereits versendetes Original
    darf seine Korrektur nicht blockieren -- dort bleibt der Fallback."""
    pdf_bytes = pdf_service.generate_rechnung_pdf(
        mandant,
        rechnung,
        kunde,
        positionen,
        storniert_rechnung=storniert_rechnung,
        vorgang_koepfe=vorgang_koepfe,
        logo_bytes=logo_bytes,
        bezug_rechnung=bezug_rechnung,
    )
    if not e_invoice_service.e_rechnung_gilt(mandant, kunde):
        return pdf_bytes, None, None
    probleme = e_invoice_service.pruefe_e_rechnung(mandant, rechnung, kunde, positionen)
    if probleme:
        if strikt:
            raise VersandFehler(versand_meldung(probleme))
        return pdf_bytes, None, None
    profil = e_invoice_service.profil_fuer(kunde)
    hinweise = privatkunden_service.hinweise_fuer(mandant, rechnung, kunde, positionen)

    try:
        netto = netto_betrag(rechnung, positionen)
        brutto = brutto_betrag(rechnung, positionen)
        dokument = e_invoice_service.baue_cii_dokument(
            mandant,
            rechnung,
            kunde,
            positionen,
            netto,
            brutto,
            bezug_rechnung=storniert_rechnung if rechnung.ist_storno else bezug_rechnung,
            angerechnete_abschlaege=angerechnete_abschlaege,
            profil=profil,
            hinweise=hinweise.texte() if hinweise is not None else None,
        )
        xml_bytes = e_invoice_service.cii_xml_bytes(dokument)
        pdf_bytes_mit_output_intent = pdf_service.generate_rechnung_pdf(
            mandant,
            rechnung,
            kunde,
            positionen,
            storniert_rechnung=storniert_rechnung,
            vorgang_koepfe=vorgang_koepfe,
            pdfa_output_intent=True,
            logo_bytes=logo_bytes,
            bezug_rechnung=bezug_rechnung,
        )
        hybrid_pdf_bytes = e_invoice_service.baue_hybrid_pdf(pdf_bytes_mit_output_intent, xml_bytes, profil)
    except Exception as exc:
        logger.exception("E-Rechnung für %s konnte nicht erzeugt werden", rechnung.rechnungsnummer)
        if strikt:
            raise VersandFehler(f"E-Rechnung konnte nicht erzeugt werden: {_kurzgrund_e_rechnung(exc)}") from exc
        return pdf_bytes, None, None
    return hybrid_pdf_bytes, xml_bytes, profil


async def beleg_bezuege_laden(
    session: AsyncSession, rechnung: Rechnung, positionen: list[RechnungPosition]
) -> tuple[Rechnung | None, list[Rechnung]]:
    """(Bezugsrechnung der Gutschrift, angerechnete Abschlaege einer
    Schlussrechnung nach Rechnungsdatum) -- der Kontext, den PDF und
    E-Rechnung ausser den Positionen brauchen."""
    bezug = await session.get(Rechnung, rechnung.bezug_rechnung_id) if rechnung.bezug_rechnung_id else None
    abschlag_ids = list(dict.fromkeys(p.abschlag_rechnung_id for p in positionen if p.abschlag_rechnung_id))
    abschlaege: list[Rechnung] = []
    if abschlag_ids:
        abschlaege = list(
            (
                await session.execute(
                    select(Rechnung).where(Rechnung.id.in_(abschlag_ids)).order_by(Rechnung.created_at, Rechnung.id)
                )
            )
            .scalars()
            .all()
        )
    return bezug, abschlaege


async def logo_bytes_laden(mandant: Mandant) -> bytes | None:
    if not mandant.logo_object_key:
        return None
    try:
        return await storage_service.download_bytes(mandant.logo_object_key)
    except Exception:
        # Ein nicht ladbares Logo darf Versand/Download der Rechnung nicht blockieren.
        return None


async def archiviere_pdf(
    session: AsyncSession,
    rechnung: Rechnung,
    mandant: Mandant,
    kunde: Kunde,
    storniert_rechnung: Rechnung | None = None,
    *,
    strikt: bool = True,
) -> bytes:
    """Erzeugt das PDF einmalig zum Versand-Zeitpunkt und speichert es
    unveraenderlich in MinIO/S3 -- spaetere Aenderungen an Firmendaten/Logo
    duerfen das bereits verschickte Dokument nicht nachtraeglich veraendern
    (GoBD-Unveraenderbarkeitsgrundsatz). Gibt die PDF-Bytes zurueck, damit
    der Aufrufer sie z.B. direkt als E-Mail-Anhang weiterverwenden kann,
    ohne sie erneut aus MinIO abzurufen."""
    positionen = await positionen_fuer(session, rechnung.id)
    koepfe = await vorgang_koepfe_map(session, positionen)
    bezug, abschlaege = await beleg_bezuege_laden(session, rechnung, positionen)
    pdf_bytes, xml_bytes, profil = _rechnung_dokument_bytes(
        rechnung,
        mandant,
        kunde,
        positionen,
        storniert_rechnung,
        koepfe,
        await logo_bytes_laden(mandant),
        strikt=strikt,
        bezug_rechnung=bezug,
        angerechnete_abschlaege=abschlaege,
    )
    key = storage_service.new_rechnung_pdf_key(rechnung.mandant_id, rechnung.id)
    aufbewahrung = aufbewahrung_fuer("rechnung", rechnung)
    bis = aufbewahrung.fristende if aufbewahrung else None
    await storage_service.upload_bytes(key, pdf_bytes, "application/pdf", aufbewahren_bis=bis)
    rechnung.pdf_object_key = key
    rechnung.pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    if xml_bytes is not None:
        xml_key = storage_service.new_rechnung_xml_key(rechnung.mandant_id, rechnung.id)
        await storage_service.upload_bytes(xml_key, xml_bytes, "application/xml", aufbewahren_bis=bis)
        rechnung.xml_object_key = xml_key
        rechnung.xml_sha256 = hashlib.sha256(xml_bytes).hexdigest()
        # GoBD: festhalten, was versendet wurde; spaetere Kundenaenderungen aendern das nicht.
        rechnung.e_rechnung_profil = profil
        rechnung.leitweg_id = (kunde.leitweg_id or "").strip() or None
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
    bezug, _ = await beleg_bezuege_laden(session, rechnung, positionen)
    return pdf_service.generate_rechnung_pdf(
        mandant,
        rechnung,
        kunde,
        positionen,
        storniert_rechnung=storniert_rechnung,
        vorgang_koepfe=await vorgang_koepfe_map(session, positionen),
        logo_bytes=await logo_bytes_laden(mandant),
        bezug_rechnung=bezug,
    )


@dataclass(frozen=True)
class ArchivObjektPruefung:
    art: str  # "pdf" | "xml"
    object_key: str
    status: str  # ok | abweichung | fehlt | kein_hash
    hash_gespeichert: str | None
    hash_berechnet: str | None


def _archivobjekte(rechnung: Rechnung) -> list[tuple[str, str, str | None]]:
    objekte = []
    if rechnung.pdf_object_key:
        objekte.append(("pdf", rechnung.pdf_object_key, rechnung.pdf_sha256))
    if rechnung.xml_object_key:
        objekte.append(("xml", rechnung.xml_object_key, rechnung.xml_sha256))
    return objekte


async def pruefe_archiv(rechnung: Rechnung) -> list[ArchivObjektPruefung]:
    """Vergleicht den heutigen Inhalt der archivierten Objekte mit dem beim Versand
    gespeicherten SHA-256. Ohne gespeicherten Hash (Altbestand) laesst sich die
    Unveraendertheit nicht beweisen -- dann nur der berechnete Wert, Status kein_hash."""
    ergebnis = []
    for art, key, gespeichert in _archivobjekte(rechnung):
        try:
            berechnet = await storage_service.sha256_object(key)
        except ClientError:
            ergebnis.append(ArchivObjektPruefung(art, key, "fehlt", gespeichert, None))
            continue
        if gespeichert is None:
            status = "kein_hash"
        else:
            status = "ok" if gespeichert == berechnet else "abweichung"
        ergebnis.append(ArchivObjektPruefung(art, key, status, gespeichert, berechnet))
    return ergebnis


async def hash_nachtragen(rechnung: Rechnung) -> list[ArchivObjektPruefung]:
    """Altbestand: setzt fehlende Hashes aus dem aktuellen S3-Inhalt. Beweist nur den
    Stand ab jetzt, nicht die Unveraendertheit seit dem Versand; die Spalten sind
    einmalig beschreibbar (Trigger), ein vorhandener Hash bleibt unberuehrt."""
    for p in await pruefe_archiv(rechnung):
        if p.status == "kein_hash" and p.hash_berechnet:
            setattr(rechnung, f"{p.art}_sha256", p.hash_berechnet)
    return await pruefe_archiv(rechnung)
