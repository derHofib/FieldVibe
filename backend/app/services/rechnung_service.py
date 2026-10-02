from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

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
    RechnungPositionRead,
    RechnungPositionVorschlag,
    RechnungRead,
    RechnungVorgangAuswahlPosten,
    RechnungVorgangKopf,
    RechnungZahlungRead,
)
from app.services import e_invoice_service, pdf_service, storage_service
from app.services.numbering_service import next_rechnungsnummer

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
    "vorgaenge",
    "betrag_netto",
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


def _read_model_aus(
    rechnung: Rechnung,
    positionen: list[RechnungPosition],
    zahlungen: list[RechnungZahlung],
    vorgaenge: list[RechnungVorgangKopf],
) -> RechnungRead:
    return RechnungRead(
        **{k: getattr(rechnung, k) for k in RechnungRead.model_fields if k not in _AUSGESCHLOSSENE_FELDER},
        betrag_netto=netto_betrag(rechnung, positionen),
        positionen=[RechnungPositionRead.model_validate(p) for p in positionen],
        zahlungen=[RechnungZahlungRead.model_validate(z) for z in zahlungen],
        vorgaenge=vorgaenge,
    )


async def to_read_model_bulk(
    session: AsyncSession, rechnungen: list[Rechnung]
) -> list[RechnungRead]:
    ids = [r.id for r in rechnungen]
    positionen_je_rechnung = await positionen_fuer_mehrere(session, ids)
    zahlungen_je_rechnung = await zahlungen_fuer_mehrere(session, ids)
    vorgaenge_je_rechnung = await vorgang_koepfe_fuer_mehrere(session, ids)
    return [
        _read_model_aus(
            r,
            positionen_je_rechnung.get(r.id, []),
            zahlungen_je_rechnung.get(r.id, []),
            vorgaenge_je_rechnung.get(r.id, []),
        )
        for r in rechnungen
    ]


async def to_read_model(session: AsyncSession, rechnung: Rechnung) -> RechnungRead:
    positionen = await positionen_fuer(session, rechnung.id)
    zahlungen = await zahlungen_fuer(session, rechnung.id)
    vorgaenge = (await vorgang_koepfe_fuer_mehrere(session, [rechnung.id]))[rechnung.id]
    return _read_model_aus(rechnung, positionen, zahlungen, vorgaenge)


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


def _rechnung_dokument_bytes(
    rechnung: Rechnung,
    mandant: Mandant,
    kunde: Kunde,
    positionen: list[RechnungPosition],
    storniert_rechnung: Rechnung | None,
    vorgang_koepfe: dict[UUID, tuple[str, str]],
    logo_bytes: bytes | None = None,
) -> tuple[bytes, bytes | None]:
    """Normales PDF ist immer der Ausgangspunkt. Nur wenn der Mandant
    e_rechnung_aktiv gesetzt hat UND alle EN16931-Pflichtangaben vorhanden
    sind, wird stattdessen ein ZUGFeRD-Hybrid-PDF (mit eingebetteter CII-XML)
    erzeugt -- sonst stiller Fallback aufs normale PDF, kein Versand-Block."""
    pdf_bytes = pdf_service.generate_rechnung_pdf(
        mandant,
        rechnung,
        kunde,
        positionen,
        storniert_rechnung=storniert_rechnung,
        vorgang_koepfe=vorgang_koepfe,
        logo_bytes=logo_bytes,
    )
    if not (mandant.firmendaten or {}).get("e_rechnung_aktiv"):
        return pdf_bytes, None
    probleme = e_invoice_service.pruefe_en16931_vollstaendigkeit(mandant, rechnung, kunde, positionen)
    if probleme:
        return pdf_bytes, None

    netto = netto_betrag(rechnung, positionen)
    brutto = brutto_betrag(rechnung, positionen)
    dokument = e_invoice_service.baue_cii_dokument(mandant, rechnung, kunde, positionen, netto, brutto)
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
    )
    hybrid_pdf_bytes = e_invoice_service.baue_hybrid_pdf(pdf_bytes_mit_output_intent, xml_bytes)
    return hybrid_pdf_bytes, xml_bytes


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
) -> bytes:
    """Erzeugt das PDF einmalig zum Versand-Zeitpunkt und speichert es
    unveraenderlich in MinIO/S3 -- spaetere Aenderungen an Firmendaten/Logo
    duerfen das bereits verschickte Dokument nicht nachtraeglich veraendern
    (GoBD-Unveraenderbarkeitsgrundsatz). Gibt die PDF-Bytes zurueck, damit
    der Aufrufer sie z.B. direkt als E-Mail-Anhang weiterverwenden kann,
    ohne sie erneut aus MinIO abzurufen."""
    positionen = await positionen_fuer(session, rechnung.id)
    koepfe = await vorgang_koepfe_map(session, positionen)
    pdf_bytes, xml_bytes = _rechnung_dokument_bytes(
        rechnung, mandant, kunde, positionen, storniert_rechnung, koepfe, await logo_bytes_laden(mandant)
    )
    key = storage_service.new_rechnung_pdf_key(rechnung.id)
    await storage_service.upload_bytes(key, pdf_bytes, "application/pdf")
    rechnung.pdf_object_key = key
    if xml_bytes is not None:
        xml_key = storage_service.new_rechnung_xml_key(rechnung.id)
        await storage_service.upload_bytes(xml_key, xml_bytes, "application/xml")
        rechnung.xml_object_key = xml_key
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
        mandant,
        rechnung,
        kunde,
        positionen,
        storniert_rechnung=storniert_rechnung,
        vorgang_koepfe=await vorgang_koepfe_map(session, positionen),
        logo_bytes=await logo_bytes_laden(mandant),
    )
