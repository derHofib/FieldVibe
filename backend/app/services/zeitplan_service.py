"""Gantt-Zeitplan fuer Projekte: Phasen, Arbeitsschritte, Meilensteine mit
Abhaengigkeiten (Ende->Anfang, Anfang->Anfang, Ende->Ende) und optionalen
Verknuepfungen (Vorgang, Bestellung/Liefertermin, Partner).

Zweigeteilt: der obere Teil (PlanElement, propagiere, aendere_element, ...)
rechnet rein auf In-Memory-Strukturen und kennt weder Datenbank noch HTTP --
dort liegt die gesamte Terminlogik und ist entsprechend direkt testbar. Der
untere Teil (lade/schreibe, element_*/abhaengigkeit_*) ist die duenne
DB-Schicht darum herum.

Gerechnet wird in Kalendertagen, Datumsbereiche sind inklusiv
(start_am..ende_am).
"""
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Iterable, Mapping
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auftrag import Auftrag
from app.models.bestellung import Bestellung
from app.models.lieferant import Lieferant
from app.models.partner import Partner
from app.models.termin import Termin
from app.models.vorgang import Vorgang
from app.models.projekt import (
    PROJEKT_ABHAENGIGKEIT_ARTEN,
    Projekt,
    ProjektAufgabe,
    ProjektAufgabeAbhaengigkeit,
    ProjektBasisplan,
    ProjektBasisplanEintrag,
    ProjektSpalte,
    ProjektVorlage,
    ProjektVorlageAbhaengigkeit,
    ProjektVorlageElement,
)
from app.models.user import User
from app.schemas.projekt import (
    ProjektVorlageAbhaengigkeitRead,
    ProjektVorlageDetail,
    ProjektVorlageElementRead,
    ProjektVorlageListe,
    ZeitplanAbhaengigkeit,
    ZeitplanAenderung,
    ZeitplanBasisplanRead,
    ZeitplanBestellungAuswahl,
    ZeitplanBestellungRef,
    ZeitplanElement,
    ZeitplanPartnerRef,
    ZeitplanRead,
    ZeitplanTerminRef,
    ZeitplanVorgangAuswahl,
    ZeitplanVorgangRef,
)

ZEITPLAN_TYPEN = ("phase", "schritt", "meilenstein")
VERSCHIEBE_MODI = ("bei_konflikt", "immer")
# Verknuepfter Vorgang in diesem Status = Schritt erledigt (storniert zaehlt
# bewusst nicht).
VORGANG_ERLEDIGT = ("abgeschlossen", "abgerechnet")
_MSG_DATUM_AUS_BESTELLUNG = "Das Datum kommt aus der Bestellung (Liefertermin)"

_NICHT_GESETZT: Any = object()


class ZeitplanFehler(Exception):
    """Basis; die Routen mappen die Unterklassen auf HTTP-Statuscodes."""


class ZeitplanRegelverstoss(ZeitplanFehler):
    """-> 400"""


class ZeitplanNichtGefunden(ZeitplanFehler):
    """-> 404"""


class ZeitplanZyklus(ZeitplanFehler):
    """-> 409"""


class ZeitplanDuplikat(ZeitplanFehler):
    """-> 409"""


# --------------------------------------------------------------------------
# Reine Logik
# --------------------------------------------------------------------------


@dataclass
class PlanElement:
    id: UUID
    typ: str
    start_am: date | None = None
    ende_am: date | None = None
    phase_id: UUID | None = None


@dataclass(frozen=True)
class PlanKante:
    vorgaenger_id: UUID
    nachfolger_id: UUID
    versatz_tage: int = 0
    art: str = "ende_anfang"


def _datiert(el: PlanElement | None) -> bool:
    return el is not None and el.start_am is not None and el.ende_am is not None


def _aktive_kanten(elemente: Mapping[UUID, PlanElement], kanten: Iterable[PlanKante]) -> list[PlanKante]:
    """Nur Verbindungen zwischen Schritten/Meilensteinen mit Datum nehmen an
    der Terminlogik teil -- Elemente ohne Datum werden ignoriert."""
    return [
        k
        for k in kanten
        if _datiert(elemente.get(k.vorgaenger_id))
        and _datiert(elemente.get(k.nachfolger_id))
        and elemente[k.vorgaenger_id].typ != "phase"
        and elemente[k.nachfolger_id].typ != "phase"
    ]


def fruehester_start(vorgaenger: PlanElement, versatz_tage: int) -> date:
    """Ende->Anfang: der Nachfolger startet am Tag nach dem Ende des
    Vorgaengers (+ Versatz). Ein Meilenstein ist ein Zeitpunkt ohne Dauer --
    dort darf der Nachfolger am selben Tag starten."""
    assert vorgaenger.start_am is not None and vorgaenger.ende_am is not None
    if vorgaenger.typ == "meilenstein":
        return vorgaenger.start_am + timedelta(days=versatz_tage)
    return vorgaenger.ende_am + timedelta(days=1 + versatz_tage)


def _verletzung_tage(el: PlanElement, vorgaenger: PlanElement, kante: PlanKante) -> int:
    """Um wie viele Tage `el` nach hinten muss, damit die Kante erfuellt ist
    (<= 0: erfuellt). Anfang->Anfang: Start des Nachfolgers >= Start des
    Vorgaengers + Versatz. Ende->Ende: Ende des Nachfolgers >= Ende des
    Vorgaengers + Versatz (die Dauer des Nachfolgers bleibt, er wandert als
    Ganzes). Ende->Anfang wie fruehester_start()."""
    assert el.start_am is not None and el.ende_am is not None
    assert vorgaenger.start_am is not None and vorgaenger.ende_am is not None
    if kante.art == "anfang_anfang":
        return (vorgaenger.start_am + timedelta(days=kante.versatz_tage) - el.start_am).days
    if kante.art == "ende_ende":
        return (vorgaenger.ende_am + timedelta(days=kante.versatz_tage) - el.ende_am).days
    return (fruehester_start(vorgaenger, kante.versatz_tage) - el.start_am).days


def hat_pfad(kanten: Iterable[PlanKante], von: UUID, nach: UUID) -> bool:
    """True, wenn `nach` von `von` aus ueber Vorgaenger->Nachfolger-Kanten
    erreichbar ist (transitiv, `von == nach` zaehlt als erreichbar)."""
    folgen: dict[UUID, list[UUID]] = defaultdict(list)
    for k in kanten:
        folgen[k.vorgaenger_id].append(k.nachfolger_id)
    gesehen = {von}
    schlange = deque([von])
    while schlange:
        aktuell = schlange.popleft()
        if aktuell == nach:
            return True
        for n in folgen[aktuell]:
            if n not in gesehen:
                gesehen.add(n)
                schlange.append(n)
    return False


def wuerde_zyklus_erzeugen(kanten: Iterable[PlanKante], vorgaenger_id: UUID, nachfolger_id: UUID) -> bool:
    """Neue Kante vorgaenger->nachfolger schliesst einen Kreis, wenn der
    Vorgaenger bereits (transitiv) ein Nachfolger des Nachfolgers ist."""
    return hat_pfad(kanten, nachfolger_id, vorgaenger_id)


def _verschiebe(el: PlanElement, tage: int) -> None:
    if tage and el.start_am is not None and el.ende_am is not None:
        el.start_am += timedelta(days=tage)
        el.ende_am += timedelta(days=tage)


def propagiere(
    elemente: dict[UUID, PlanElement],
    kanten: Iterable[PlanKante],
    modus: str,
    ausgangspunkte: Mapping[UUID, int],
    erzwinge: Iterable[UUID] = (),
    start_deltas: Mapping[UUID, int] | None = None,
    fest: Iterable[UUID] = (),
) -> set[UUID]:
    """Zieht alle transitiven Nachfolger der `ausgangspunkte` nach.

    `ausgangspunkte` bildet die bereits (vom Aufrufer) geaenderten Elemente
    auf die Aenderung ihres Endes in Tagen ab (positiv = spaeter);
    `start_deltas` analog fuer den Start (Default: dasselbe Delta, also eine
    reine Verschiebung) -- relevant nur fuer Anfang->Anfang im Modus
    'immer'. `fest` sind Elemente, deren Datum von aussen vorgegeben ist
    (Meilenstein mit Bestellung): sie werden wie Ausgangspunkte ohne
    Aenderung behandelt und nie verschoben. Ausgangspunkte selbst
    werden nie angefasst -- auch nicht, wenn sie ihren eigenen Vorgaenger
    verletzen; das ist eine explizite Nutzerentscheidung. `erzwinge` sind
    zusaetzliche Elemente (z. B. der Nachfolger einer neuen Verbindung), bei
    denen die Konflikt-Regel durchgesetzt wird, auch ohne dass ein Vorgaenger
    sich bewegt hat; sie werden samt ihrer Nachfolger verarbeitet.

    Verarbeitet wird in topologischer Reihenfolge, damit ein Nachfolger mit
    mehreren Vorgaengern (Diamant) erst nach allen betroffenen Vorgaengern
    bewertet wird. Fuer jeden Nachfolger N:

    * Modus 'immer': N wird zuerst um das Delta verschoben, um das sich das
      Ende seiner bewegten Vorgaenger geaendert hat (auch nach vorne). Hat
      N mehrere bewegte Vorgaenger, gilt das groesste Delta (bei Verschiebung
      nach vorne also das kleinste Stueck nach vorne -- vorsichtig). Je
      Kante zaehlt das Delta, das zur Art passt: Start des Vorgaengers bei
      Anfang->Anfang, sonst sein Ende.
    * Beide Modi: danach wird die Konflikt-Regel durchgesetzt. N darf keinen
      Vorgaenger verletzen: die strengste Kante (Maximum ueber ALLE
      Vorgaenger, auch unbewegte, und alle Arten) bestimmt, wie weit N nach
      hinten geschoben wird. Die Dauer bleibt immer erhalten.
    * Modus 'bei_konflikt': es findet nur diese zweite Regel statt -- N
      wandert nie nach vorne, ein vorhandener Puffer bleibt erhalten.

    Rueckgabe: Menge der durch die Propagation (nicht der Ausgangspunkte)
    verschobenen Elemente.
    """
    if modus not in VERSCHIEBE_MODI:
        raise ValueError(f"Unbekannter Verschiebe-Modus: {modus}")
    erzwinge = set(erzwinge)
    aktiv = _aktive_kanten(elemente, kanten)
    vorgaenger_von: dict[UUID, list[PlanKante]] = defaultdict(list)
    nachfolger_von: dict[UUID, list[UUID]] = defaultdict(list)
    for k in aktiv:
        vorgaenger_von[k.nachfolger_id].append(k)
        nachfolger_von[k.vorgaenger_id].append(k.nachfolger_id)

    betroffen: set[UUID] = set(ausgangspunkte) | erzwinge
    schlange = deque(betroffen)
    while schlange:
        aktuell = schlange.popleft()
        for n in nachfolger_von[aktuell]:
            if n not in betroffen:
                betroffen.add(n)
                schlange.append(n)

    eingangsgrad = {n: 0 for n in betroffen}
    for k in aktiv:
        if k.vorgaenger_id in betroffen and k.nachfolger_id in betroffen:
            eingangsgrad[k.nachfolger_id] += 1
    bereit = deque(n for n, grad in eingangsgrad.items() if grad == 0)
    reihenfolge: list[UUID] = []
    while bereit:
        aktuell = bereit.popleft()
        reihenfolge.append(aktuell)
        for n in nachfolger_von[aktuell]:
            if n in eingangsgrad:
                eingangsgrad[n] -= 1
                if eingangsgrad[n] == 0:
                    bereit.append(n)
    if len(reihenfolge) != len(betroffen):
        raise ZeitplanZyklus("Diese Verbindung würde einen Kreis erzeugen")

    ende_delta: dict[UUID, int] = dict(ausgangspunkte)
    start_delta: dict[UUID, int] = dict(ausgangspunkte if start_deltas is None else start_deltas)
    fest = set(fest)
    verschoben: set[UUID] = set()
    for n in reihenfolge:
        if n in ausgangspunkte:
            start_delta.setdefault(n, ende_delta[n])
            continue
        if n in fest:
            ende_delta[n] = start_delta[n] = 0
            continue
        el = elemente[n]
        alt_start, alt_ende = el.start_am, el.ende_am
        eingehend = vorgaenger_von[n]

        if modus == "immer":
            deltas = [
                (start_delta if k.art == "anfang_anfang" else ende_delta)[k.vorgaenger_id]
                for k in eingehend
                if k.vorgaenger_id in ende_delta
            ]
            if deltas:
                _verschiebe(el, max(deltas))

        if eingehend:
            noetig = max(_verletzung_tage(el, elemente[k.vorgaenger_id], k) for k in eingehend)
            if noetig > 0:
                _verschiebe(el, noetig)

        assert el.start_am is not None and alt_start is not None
        assert el.ende_am is not None and alt_ende is not None
        start_delta[n] = (el.start_am - alt_start).days
        delta = (el.ende_am - alt_ende).days
        ende_delta[n] = delta
        if delta:
            verschoben.add(n)
    return verschoben


def aktualisiere_phasenspannen(elemente: dict[UUID, PlanElement]) -> set[UUID]:
    """Setzt start_am/ende_am jeder Phase auf min/max ihrer Elemente mit
    Datum (keins -> None). Rueckgabe: Phasen, deren Spanne sich geaendert hat."""
    kinder: dict[UUID, list[PlanElement]] = defaultdict(list)
    for el in elemente.values():
        if el.typ != "phase" and el.phase_id is not None and _datiert(el):
            kinder[el.phase_id].append(el)
    geaendert: set[UUID] = set()
    for el in elemente.values():
        if el.typ != "phase":
            continue
        sicht = kinder.get(el.id, [])
        start = min((k.start_am for k in sicht if k.start_am), default=None)
        ende = max((k.ende_am for k in sicht if k.ende_am), default=None)
        if (el.start_am, el.ende_am) != (start, ende):
            el.start_am, el.ende_am = start, ende
            geaendert.add(el.id)
    return geaendert


def verschiebe_phase(
    elemente: dict[UUID, PlanElement], phase_id: UUID, tage: int, fest: Iterable[UUID] = ()
) -> dict[UUID, int]:
    """Verschiebt alle Elemente mit Datum der Phase um `tage`. Rueckgabe: die
    bewegten Elemente mit ihrem Ende-Delta (= `tage`), als `ausgangspunkte`
    fuer propagiere() geeignet. `fest` bleiben stehen (Datum von aussen)."""
    bewegt: dict[UUID, int] = {}
    fest = set(fest)
    for el in elemente.values():
        if el.typ != "phase" and el.phase_id == phase_id and _datiert(el) and el.id not in fest:
            _verschiebe(el, tage)
            bewegt[el.id] = tage
    return bewegt


@dataclass
class KritischerPfad:
    """Ergebnis der CPM-Rechnung. `puffer` enthaelt nur datierte Schritte/
    Meilensteine (Phasen und Elemente ohne Datum fehlen -> "kein Puffer")."""

    puffer: dict[UUID, int]
    kritisch: set[UUID]
    kritische_kanten: set[tuple[UUID, UUID]]


def _topologisch(knoten: Iterable[UUID], kanten: list[PlanKante]) -> list[UUID]:
    """Kahn; Knoten in einem (eigentlich ausgeschlossenen) Kreis fehlen."""
    knoten = set(knoten)
    folgen: dict[UUID, list[UUID]] = defaultdict(list)
    grad = {n: 0 for n in knoten}
    for k in kanten:
        folgen[k.vorgaenger_id].append(k.nachfolger_id)
        grad[k.nachfolger_id] += 1
    bereit = deque(n for n, g in grad.items() if g == 0)
    reihenfolge: list[UUID] = []
    while bereit:
        aktuell = bereit.popleft()
        reihenfolge.append(aktuell)
        for n in folgen[aktuell]:
            grad[n] -= 1
            if grad[n] == 0:
                bereit.append(n)
    return reihenfolge


def _dauer_diff(el: PlanElement) -> int:
    assert el.start_am is not None and el.ende_am is not None
    return (el.ende_am - el.start_am).days


def berechne_kritischen_pfad(elemente: Mapping[UUID, PlanElement], kanten: Iterable[PlanKante]) -> KritischerPfad:
    """CPM ueber alle datierten Schritte/Meilensteine (Phasen und Elemente
    ohne Datum nehmen nicht teil). Vorwaerts gilt der tatsaechliche Termin
    (nicht ein neu berechneter frueheste-Lage-Plan), rueckwaerts wird vom
    Projektende (max ende_am) aus der spaeteste Start/Ende bestimmt:
    Gesamtpuffer = spaetester Start - tatsaechlicher Start; kritisch =
    Puffer <= 0 (negativ: eine Verbindung ist bewusst verletzt). Jedes
    Element muss zudem spaetestens am Projektende enden."""
    aktiv = _aktive_kanten(elemente, kanten)
    knoten = {
        i for i, el in elemente.items() if el.typ != "phase" and _datiert(el)
    }
    if not knoten:
        return KritischerPfad({}, set(), set())
    projektende = max(elemente[i].ende_am for i in knoten)  # type: ignore[type-var]
    nachfolger_kanten: dict[UUID, list[PlanKante]] = defaultdict(list)
    for k in aktiv:
        nachfolger_kanten[k.vorgaenger_id].append(k)

    # Spaetestes Ende je Element; Senken: Projektende.
    spaetestes_ende: dict[UUID, date] = {}
    spaetester_start: dict[UUID, date] = {}
    for i in reversed(_topologisch(knoten, aktiv)):
        el = elemente[i]
        grenzen = [projektende]
        for k in nachfolger_kanten[i]:
            n_start = spaetester_start[k.nachfolger_id]
            n_ende = spaetestes_ende[k.nachfolger_id]
            if k.art == "anfang_anfang":
                grenzen.append(n_start - timedelta(days=k.versatz_tage) + timedelta(days=_dauer_diff(el)))
            elif k.art == "ende_ende":
                grenzen.append(n_ende - timedelta(days=k.versatz_tage))
            else:
                # Gegenstueck zu fruehester_start(): Meilenstein ohne Dauer
                # darf am selben Tag wie sein Nachfolger liegen.
                luecke = 0 if el.typ == "meilenstein" else 1
                grenzen.append(n_start - timedelta(days=luecke + k.versatz_tage))
        spaetestes_ende[i] = min(grenzen)
        spaetester_start[i] = spaetestes_ende[i] - timedelta(days=_dauer_diff(el))

    puffer = {i: (spaetester_start[i] - elemente[i].start_am).days for i in spaetester_start}  # type: ignore[operator]
    kritisch = {i for i, p in puffer.items() if p <= 0}
    kritische_kanten = {
        (k.vorgaenger_id, k.nachfolger_id)
        for k in aktiv
        if k.vorgaenger_id in kritisch
        and k.nachfolger_id in kritisch
        and _verletzung_tage(elemente[k.nachfolger_id], elemente[k.vorgaenger_id], k) == 0
    }
    return KritischerPfad(puffer, kritisch, kritische_kanten)


def straffe_plan(
    elemente: dict[UUID, PlanElement],
    kanten: Iterable[PlanKante],
    fest: Iterable[UUID] = (),
    phase_id: UUID | None = None,
) -> set[UUID]:
    """Setzt jedes nicht feste Element mit mindestens einem (datierten)
    Vorgaenger auf seinen fruehestmoeglichen Termin laut aller eingehenden
    Verbindungen -- auch nach vorne; die Dauer bleibt. Topologisch, damit
    ein Nachfolger die bereits gestrafften Vorgaenger sieht. Mit `phase_id`
    werden nur Elemente dieser Phase angefasst, alle anderen (auch
    Vorgaenger ausserhalb) zaehlen als feste Randbedingung. Aktualisiert die
    Phasenspannen. Rueckgabe: ids der Elemente (ohne Phasen), deren Termin
    sich geaendert hat."""
    fest = set(fest)
    aktiv = _aktive_kanten(elemente, kanten)
    eingehend: dict[UUID, list[PlanKante]] = defaultdict(list)
    for k in aktiv:
        eingehend[k.nachfolger_id].append(k)
    knoten = {i for i, el in elemente.items() if el.typ != "phase" and _datiert(el)}
    geaendert: set[UUID] = set()
    for i in _topologisch(knoten, aktiv):
        el = elemente[i]
        if i in fest or not eingehend[i] or (phase_id is not None and el.phase_id != phase_id):
            continue
        d = timedelta(days=_dauer_diff(el))
        fruehester = max(_fruehester_start_fuer(elemente[k.vorgaenger_id], k, d) for k in eingehend[i])
        if fruehester != el.start_am:
            el.start_am, el.ende_am = fruehester, fruehester + d
            geaendert.add(i)
    aktualisiere_phasenspannen(elemente)
    return geaendert


def _fruehester_start_fuer(vorgaenger: PlanElement, kante: PlanKante, dauer: timedelta) -> date:
    assert vorgaenger.start_am is not None and vorgaenger.ende_am is not None
    if kante.art == "anfang_anfang":
        return vorgaenger.start_am + timedelta(days=kante.versatz_tage)
    if kante.art == "ende_ende":
        return vorgaenger.ende_am + timedelta(days=kante.versatz_tage) - dauer
    return fruehester_start(vorgaenger, kante.versatz_tage)



def _normalisiere_zeitraum(typ: str, start: date | None, ende: date | None) -> tuple[date | None, date | None]:
    """Nur ein Datum gesetzt -> Ein-Tages-Zeitraum; Meilenstein: ende = start."""
    if typ == "meilenstein":
        tag = start if start is not None else ende
        return tag, tag
    if start is None and ende is not None:
        start = ende
    elif ende is None and start is not None:
        ende = start
    if start is not None and ende is not None and ende < start:
        raise ZeitplanRegelverstoss("Ende liegt vor dem Start")
    return start, ende


def aendere_element(
    elemente: dict[UUID, PlanElement],
    kanten: Iterable[PlanKante],
    modus: str,
    element_id: UUID,
    *,
    start_am: Any = _NICHT_GESETZT,
    ende_am: Any = _NICHT_GESETZT,
    fest: Iterable[UUID] = (),
) -> set[UUID]:
    """Aendert den Zeitraum eines Elements, zieht Nachfolger nach und
    aktualisiert alle Phasenspannen. Rueckgabe: ids aller Elemente (inkl.
    des angefragten und betroffener Phasen), deren Datum sich geaendert hat.

    Verschieben = beide Daten um dasselbe Delta, Verlaengern/Verkuerzen =
    nur ende_am; die Propagation haengt allein am geaenderten Ende. Phase:
    Spanne ist abgeleitet, erlaubt ist nur das gemeinsame Verschieben
    (start und ende um dasselbe Delta) -- alles andere ist ein
    Regelverstoss."""
    el = elemente[element_id]
    vorher = {i: (e.start_am, e.ende_am) for i, e in elemente.items()}
    kanten = list(kanten)
    fest = set(fest)
    start_deltas: dict[UUID, int] | None = None

    if el.typ == "phase":
        if start_am is _NICHT_GESETZT and ende_am is _NICHT_GESETZT:
            return set()
        if start_am is _NICHT_GESETZT or ende_am is _NICHT_GESETZT or start_am is None or ende_am is None:
            raise ZeitplanRegelverstoss(
                "Phasen können nur als Ganzes verschoben werden (Start und Ende gemeinsam)"
            )
        if el.start_am is None or el.ende_am is None:
            raise ZeitplanRegelverstoss("Eine Phase ohne datierte Elemente kann nicht verschoben werden")
        delta_start = (start_am - el.start_am).days
        if delta_start != (ende_am - el.ende_am).days:
            raise ZeitplanRegelverstoss(
                "Phasen können nur verschoben werden -- die Dauer ergibt sich aus den Elementen"
            )
        ausgangspunkte = verschiebe_phase(elemente, element_id, delta_start, fest)
    else:
        alt_start, alt_ende = el.start_am, el.ende_am
        neu_start = alt_start if start_am is _NICHT_GESETZT else start_am
        neu_ende = alt_ende if ende_am is _NICHT_GESETZT else ende_am
        if el.typ == "meilenstein" and start_am is _NICHT_GESETZT and ende_am is not _NICHT_GESETZT:
            neu_start = ende_am
        # Nur ein Datum angegeben (Start verschoben): bei bestehendem Zeitraum
        # bleibt das andere Ende stehen und wird gegen den Start geprueft.
        neu_start, neu_ende = _normalisiere_zeitraum(el.typ, neu_start, neu_ende)
        el.start_am, el.ende_am = neu_start, neu_ende
        if neu_ende is not None and alt_ende is not None:
            ausgangspunkte = {element_id: (neu_ende - alt_ende).days}
            if alt_start is not None and neu_start is not None:
                start_deltas = {element_id: (neu_start - alt_start).days}
        elif neu_ende is not None:
            # Erstmals datiert: kein Delta, aber Nachfolger (falls
            # Verbindungen existieren) gegen das neue Ende pruefen.
            ausgangspunkte = {element_id: 0}
        else:
            ausgangspunkte = {}

    if ausgangspunkte:
        propagiere(elemente, kanten, modus, ausgangspunkte, start_deltas=start_deltas, fest=fest)
    aktualisiere_phasenspannen(elemente)
    return {i for i, e in elemente.items() if (e.start_am, e.ende_am) != vorher[i]}


# --------------------------------------------------------------------------
# DB-Schicht
# --------------------------------------------------------------------------


async def _lade(
    session: AsyncSession, projekt_id: UUID
) -> tuple[dict[UUID, ProjektAufgabe], list[ProjektAufgabeAbhaengigkeit]]:
    zeilen = (
        await session.execute(
            select(ProjektAufgabe)
            .where(
                ProjektAufgabe.projekt_id == projekt_id,
                ProjektAufgabe.typ.in_(ZEITPLAN_TYPEN),
                ProjektAufgabe.geloescht_am.is_(None),
            )
            .execution_options(populate_existing=True)
        )
    ).scalars()
    orm = {a.id: a for a in zeilen}
    deps = (
        await session.execute(
            select(ProjektAufgabeAbhaengigkeit)
            .where(ProjektAufgabeAbhaengigkeit.projekt_id == projekt_id)
            .execution_options(populate_existing=True)
        )
    ).scalars()
    # Verbindungen zu weich geloeschten Elementen (z. B. ueber die Kanban-
    # Loeschroute) zaehlen nicht mehr.
    return orm, [d for d in deps if d.vorgaenger_id in orm and d.nachfolger_id in orm]


def _plan_aus(orm: Mapping[UUID, ProjektAufgabe]) -> dict[UUID, PlanElement]:
    return {
        i: PlanElement(id=i, typ=a.typ, start_am=a.start_am, ende_am=a.ende_am, phase_id=a.plan_phase_id)
        for i, a in orm.items()
    }


def _kanten_aus(deps: Iterable[ProjektAufgabeAbhaengigkeit]) -> list[PlanKante]:
    return [PlanKante(d.vorgaenger_id, d.nachfolger_id, d.versatz_tage, d.art) for d in deps]


def _schreibe_zurueck(orm: Mapping[UUID, ProjektAufgabe], plan: Mapping[UUID, PlanElement]) -> None:
    for i, el in plan.items():
        a = orm[i]
        if (a.start_am, a.ende_am) != (el.start_am, el.ende_am):
            a.start_am, a.ende_am = el.start_am, el.ende_am
        a.plan_phase_id = el.phase_id


async def _projekt_modus(session: AsyncSession, projekt: Projekt) -> str:
    # projekt.verschiebe_modus ist nach einem PATCH expired -- frisch laden.
    await session.refresh(projekt, attribute_names=["verschiebe_modus"])
    return projekt.verschiebe_modus


# Schluessel in session.info: die Zeitplan-Routen haengen die erlaubten Kunden
# (None = unbeschraenkt) per Router-Dependency an die Request-Session, damit
# jede der vielen ZeitplanRead-liefernden Mutationen dieselbe Schwaerzung bekommt.
ERLAUBTE_KUNDEN_INFO_KEY = "zeitplan_erlaubte_kunden"


async def lese_zeitplan(
    session: AsyncSession, projekt: Projekt, basisplan_id: UUID | None = None
) -> ZeitplanRead:
    erlaubte_kunden: set[UUID] | None = session.info.get(ERLAUBTE_KUNDEN_INFO_KEY)
    modus = await _projekt_modus(session, projekt)
    basis: dict[UUID, tuple[date, date]] = {}
    if basisplan_id is not None:
        await _basisplan(session, projekt.id, basisplan_id)
        basis = {
            e.element_id: (e.start_am, e.ende_am)
            for e in (
                await session.execute(
                    select(ProjektBasisplanEintrag).where(ProjektBasisplanEintrag.basisplan_id == basisplan_id)
                )
            ).scalars()
        }
    zeilen = (
        await session.execute(
            select(
                ProjektAufgabe.id,
                ProjektAufgabe.typ,
                ProjektAufgabe.titel,
                ProjektAufgabe.plan_phase_id,
                ProjektAufgabe.start_am,
                ProjektAufgabe.ende_am,
                ProjektAufgabe.fortschritt,
                ProjektAufgabe.plan_reihenfolge,
                ProjektAufgabe.zugewiesen_an,
                User.name,
                ProjektAufgabe.erledigt_am,
                ProjektAufgabe.vorgang_id,
                ProjektAufgabe.bestellung_id,
                ProjektAufgabe.partner_id,
            )
            .outerjoin(User, User.id == ProjektAufgabe.zugewiesen_an)
            .where(
                ProjektAufgabe.projekt_id == projekt.id,
                ProjektAufgabe.typ.in_(ZEITPLAN_TYPEN),
                ProjektAufgabe.geloescht_am.is_(None),
            )
            .order_by(ProjektAufgabe.plan_reihenfolge, ProjektAufgabe.created_at)
        )
    ).all()

    # Je Verknuepfungsart genau eine Query fuer alle Elemente (kein N+1).
    vorgang_ids = {r[11] for r in zeilen if r[11] is not None}
    vorgaenge: dict[UUID, ZeitplanVorgangRef] = {}
    termine: dict[UUID, list[ZeitplanTerminRef]] = defaultdict(list)
    if vorgang_ids:
        for v in (
            await session.execute(
                select(
                    Vorgang.id, Vorgang.vorgangsnummer, Vorgang.titel, Vorgang.status, Vorgang.kunde_id
                ).where(Vorgang.id.in_(vorgang_ids), Vorgang.geloescht_am.is_(None))
            )
        ).all():
            # Element bleibt sichtbar, der Vorgang eines nicht zugewiesenen
            # Kunden wird nicht mitgeliefert (damit entfallen auch Termine).
            if erlaubte_kunden is not None and v[4] not in erlaubte_kunden:
                continue
            vorgaenge[v[0]] = ZeitplanVorgangRef(id=v[0], vorgangsnummer=v[1], titel=v[2], status=v[3])
        for t in (
            await session.execute(
                select(Termin.id, Termin.vorgang_id, Termin.start_at, Termin.ende_at, User.name)
                .outerjoin(User, User.id == Termin.techniker_id)
                .where(Termin.vorgang_id.in_(list(vorgaenge)), Termin.geloescht_am.is_(None))
                .order_by(Termin.start_at, Termin.id)
            )
        ).all():
            termine[t[1]].append(ZeitplanTerminRef(id=t[0], start=t[2], ende=t[3], techniker_name=t[4]))

    bestellung_ids = {r[12] for r in zeilen if r[12] is not None}
    bestellungen: dict[UUID, ZeitplanBestellungRef] = {}
    if bestellung_ids:
        for b in (
            await session.execute(
                select(Bestellung.id, Bestellung.bestellnummer, Bestellung.status, Bestellung.liefertermin, Lieferant.name)
                .outerjoin(Lieferant, Lieferant.id == Bestellung.lieferant_id)
                .where(Bestellung.id.in_(bestellung_ids), Bestellung.geloescht_am.is_(None))
            )
        ).all():
            bestellungen[b[0]] = ZeitplanBestellungRef(
                id=b[0], bestellnummer=b[1], status=b[2], liefertermin=b[3], lieferant_name=b[4]
            )

    partner_ids = {r[13] for r in zeilen if r[13] is not None}
    partner: dict[UUID, ZeitplanPartnerRef] = {}
    if partner_ids:
        for p in (await session.execute(select(Partner.id, Partner.name).where(Partner.id.in_(partner_ids)))).all():
            partner[p[0]] = ZeitplanPartnerRef(id=p[0], name=p[1])

    ids = {r[0] for r in zeilen}
    deps = [
        d
        for d in (
            await session.execute(
                select(ProjektAufgabeAbhaengigkeit)
                .where(ProjektAufgabeAbhaengigkeit.projekt_id == projekt.id)
                .order_by(ProjektAufgabeAbhaengigkeit.created_at)
            )
        ).scalars()
        if d.vorgaenger_id in ids and d.nachfolger_id in ids
    ]
    cpm = berechne_kritischen_pfad(
        {r[0]: PlanElement(id=r[0], typ=r[1], start_am=r[4], ende_am=r[5], phase_id=r[3]) for r in zeilen},
        _kanten_aus(deps),
    )

    elemente = []
    for r in zeilen:
        vorgang = vorgaenge.get(r[11]) if r[11] is not None else None
        erledigt = vorgang.status in VORGANG_ERLEDIGT if vorgang is not None else r[10] is not None
        bestellung = bestellungen.get(r[12]) if r[12] is not None else None
        elemente.append(
            ZeitplanElement(
                id=r[0],
                typ=r[1],
                titel=r[2],
                phase_id=r[3],
                start_am=r[4],
                ende_am=r[5],
                fortschritt=100 if vorgang is not None and erledigt else r[6],
                plan_reihenfolge=r[7],
                zugewiesen_an=r[8],
                zugewiesen_name=r[9],
                erledigt=erledigt,
                vorgang=vorgang,
                termine=termine.get(r[11], []) if vorgang is not None else [],
                bestellung=bestellung,
                datum_gesperrt=bestellung is not None,
                partner=partner.get(r[13]) if r[13] is not None else None,
                puffer_tage=cpm.puffer.get(r[0]),
                kritisch=r[0] in cpm.kritisch,
                basis_start_am=basis[r[0]][0] if r[0] in basis else None,
                basis_ende_am=basis[r[0]][1] if r[0] in basis else None,
                abweichung_tage=(r[5] - basis[r[0]][1]).days if r[0] in basis and r[5] is not None else None,
            )
        )
    # Phasen zuerst (nach plan_reihenfolge), danach die Elemente -- das
    # Frontend gruppiert selbst anhand phase_id.
    elemente.sort(key=lambda e: (e.typ != "phase", e.plan_reihenfolge))
    return ZeitplanRead(
        projekt_id=projekt.id,
        verschiebe_modus=modus,  # type: ignore[arg-type]
        elemente=elemente,
        abhaengigkeiten=[
            ZeitplanAbhaengigkeit(
                id=d.id,
                vorgaenger_id=d.vorgaenger_id,
                nachfolger_id=d.nachfolger_id,
                art=d.art,  # type: ignore[arg-type]
                versatz_tage=d.versatz_tage,
                kritisch=(d.vorgaenger_id, d.nachfolger_id) in cpm.kritische_kanten,
            )
            for d in deps
        ],
    )


async def _pruefe_nutzer(session: AsyncSession, mandant_id: UUID, user_id: UUID | None) -> None:
    if user_id is None:
        return
    gefunden = (
        await session.execute(select(User.id).where(User.id == user_id, User.mandant_id == mandant_id))
    ).first()
    if gefunden is None:
        raise ZeitplanRegelverstoss("Nutzer nicht gefunden oder gehört nicht zum eigenen Mandanten")


def _pruefe_phase(orm: Mapping[UUID, ProjektAufgabe], phase_id: UUID | None) -> None:
    if phase_id is None:
        return
    phase = orm.get(phase_id)
    if phase is None or phase.typ != "phase":
        raise ZeitplanRegelverstoss("Phase nicht gefunden oder gehört nicht zu diesem Projekt")


def _nur_typ(el_typ: str, erlaubt: str, meldung: str) -> None:
    if el_typ != erlaubt:
        raise ZeitplanRegelverstoss(meldung)


async def _pruefe_vorgang(
    session: AsyncSession,
    orm: Mapping[UUID, ProjektAufgabe],
    element_id: UUID | None,
    vorgang_id: UUID,
    erlaubte_kunden: set[UUID] | None,
) -> None:
    # RLS blendet fremde Mandanten aus -> hier "nicht gefunden".
    v = await session.get(Vorgang, vorgang_id)
    if (
        v is None
        or v.geloescht_am is not None
        or (erlaubte_kunden is not None and v.kunde_id not in erlaubte_kunden)
    ):
        raise ZeitplanRegelverstoss("Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten")
    if any(a.vorgang_id == vorgang_id and a.id != element_id for a in orm.values()):
        raise ZeitplanRegelverstoss("Dieser Vorgang ist in diesem Zeitplan bereits mit einem Element verknüpft")


async def _aktive_bestellung(session: AsyncSession, bestellung_id: UUID | None) -> Bestellung | None:
    if bestellung_id is None:
        return None
    b = await session.get(Bestellung, bestellung_id)
    return b if b is not None and b.geloescht_am is None else None


async def _pruefe_bestellung(session: AsyncSession, bestellung_id: UUID) -> Bestellung:
    b = await _aktive_bestellung(session, bestellung_id)
    if b is None:
        raise ZeitplanRegelverstoss("Bestellung nicht gefunden oder gehört nicht zum eigenen Mandanten")
    return b


async def _pruefe_partner(session: AsyncSession, partner_id: UUID) -> None:
    p = await session.get(Partner, partner_id)
    if p is None or not p.aktiv:
        raise ZeitplanRegelverstoss("Partner nicht gefunden, inaktiv oder gehört nicht zum eigenen Mandanten")


async def _feste_ids(session: AsyncSession, orm: Mapping[UUID, ProjektAufgabe]) -> set[UUID]:
    """Meilensteine mit (nicht gelöschter) Bestellung: ihr Datum gehört dem
    Liefertermin und darf von der Propagation nicht verschoben werden."""
    ids = {a.bestellung_id for a in orm.values() if a.bestellung_id is not None}
    if not ids:
        return set()
    aktiv = set(
        (
            await session.execute(
                select(Bestellung.id).where(Bestellung.id.in_(ids), Bestellung.geloescht_am.is_(None))
            )
        ).scalars()
    )
    return {a.id for a in orm.values() if a.bestellung_id in aktiv}


def _naechste_reihenfolge(orm: Mapping[UUID, ProjektAufgabe], typ: str, phase_id: UUID | None) -> int:
    gruppe = [
        a.plan_reihenfolge
        for a in orm.values()
        if (a.typ == "phase" if typ == "phase" else (a.typ != "phase" and a.plan_phase_id == phase_id))
    ]
    return max(gruppe, default=-1) + 1


def _setze_fortschritt(a: ProjektAufgabe, fortschritt: int) -> None:
    a.fortschritt = fortschritt
    a.erledigt_am = datetime.now(UTC) if fortschritt >= 100 else None


async def element_anlegen(
    session: AsyncSession,
    projekt: Projekt,
    *,
    mandant_id: UUID,
    user_id: UUID,
    typ: str,
    titel: str,
    phase_id: UUID | None,
    start_am: date | None,
    ende_am: date | None,
    zugewiesen_an: UUID | None,
    vorgang_id: UUID | None = None,
    bestellung_id: UUID | None = None,
    partner_id: UUID | None = None,
    erlaubte_kunden: set[UUID] | None = None,
) -> None:
    if typ not in ZEITPLAN_TYPEN:
        raise ZeitplanRegelverstoss("Unbekannter Typ")
    orm, _ = await _lade(session, projekt.id)
    if typ == "phase":
        if phase_id is not None:
            raise ZeitplanRegelverstoss("Phasen können nicht in Phasen liegen")
        # Phasen-Spanne ist abgeleitet.
        start_am = ende_am = None
    _pruefe_phase(orm, phase_id)
    await _pruefe_nutzer(session, mandant_id, zugewiesen_an)
    if vorgang_id is not None:
        _nur_typ(typ, "schritt", "Ein Vorgang kann nur mit einem Arbeitsschritt verknüpft werden")
        await _pruefe_vorgang(session, orm, None, vorgang_id, erlaubte_kunden)
    if partner_id is not None:
        _nur_typ(typ, "schritt", "Ein Fremdgewerk kann nur einem Arbeitsschritt zugeordnet werden")
        await _pruefe_partner(session, partner_id)
    if bestellung_id is not None:
        _nur_typ(typ, "meilenstein", "Eine Bestellung kann nur mit einem Meilenstein verknüpft werden")
        bestellung = await _pruefe_bestellung(session, bestellung_id)
        if start_am is not None or ende_am is not None:
            raise ZeitplanRegelverstoss(_MSG_DATUM_AUS_BESTELLUNG)
        start_am = ende_am = bestellung.liefertermin
    start_am, ende_am = _normalisiere_zeitraum(typ, start_am, ende_am)

    spalte_id = None
    if typ == "schritt":
        spalte_id = (
            await session.execute(
                select(ProjektSpalte.id)
                .where(ProjektSpalte.projekt_id == projekt.id)
                .order_by(ProjektSpalte.reihenfolge)
                .limit(1)
            )
        ).scalar_one_or_none()

    session.add(
        ProjektAufgabe(
            mandant_id=mandant_id,
            projekt_id=projekt.id,
            spalte_id=spalte_id,
            typ=typ,
            titel=titel,
            start_am=start_am,
            ende_am=ende_am,
            plan_phase_id=phase_id,
            plan_reihenfolge=_naechste_reihenfolge(orm, typ, phase_id),
            zugewiesen_an=zugewiesen_an,
            vorgang_id=vorgang_id,
            bestellung_id=bestellung_id,
            partner_id=partner_id,
            erstellt_von=user_id,
        )
    )
    await session.flush()
    await _aktualisiere_phasen(session, projekt.id)


async def _aktualisiere_phasen(session: AsyncSession, projekt_id: UUID) -> None:
    orm, _ = await _lade(session, projekt_id)
    plan = _plan_aus(orm)
    aktualisiere_phasenspannen(plan)
    _schreibe_zurueck(orm, plan)
    await session.flush()


async def element_aendern(
    session: AsyncSession,
    projekt: Projekt,
    element_id: UUID,
    aenderungen: Mapping[str, Any],
    mandant_id: UUID,
    erlaubte_kunden: set[UUID] | None = None,
) -> None:
    """`aenderungen` enthaelt nur tatsaechlich gesendete Felder (exclude_unset)."""
    orm, deps = await _lade(session, projekt.id)
    a = orm.get(element_id)
    if a is None:
        raise ZeitplanNichtGefunden("Element nicht gefunden")
    plan = _plan_aus(orm)

    if "titel" in aenderungen:
        a.titel = aenderungen["titel"]
    if "fortschritt" in aenderungen:
        _setze_fortschritt(a, aenderungen["fortschritt"])
    if "zugewiesen_an" in aenderungen:
        await _pruefe_nutzer(session, mandant_id, aenderungen["zugewiesen_an"])
        a.zugewiesen_an = aenderungen["zugewiesen_an"]
    if "phase_id" in aenderungen:
        neue_phase = aenderungen["phase_id"]
        if a.typ == "phase" and neue_phase is not None:
            raise ZeitplanRegelverstoss("Phasen können nicht in Phasen liegen")
        _pruefe_phase(orm, neue_phase)
        if neue_phase != a.plan_phase_id:
            a.plan_phase_id = neue_phase
            plan[element_id].phase_id = neue_phase
            # Ans Ende der Zielgruppe, sofern nicht zugleich explizit gesetzt.
            if "plan_reihenfolge" not in aenderungen:
                a.plan_reihenfolge = _naechste_reihenfolge(orm, a.typ, neue_phase)
    if "plan_reihenfolge" in aenderungen:
        a.plan_reihenfolge = aenderungen["plan_reihenfolge"]

    zeit = {k: aenderungen[k] for k in ("start_am", "ende_am") if k in aenderungen}
    if "vorgang_id" in aenderungen:
        if aenderungen["vorgang_id"] is not None:
            _nur_typ(a.typ, "schritt", "Ein Vorgang kann nur mit einem Arbeitsschritt verknüpft werden")
            await _pruefe_vorgang(session, orm, element_id, aenderungen["vorgang_id"], erlaubte_kunden)
        a.vorgang_id = aenderungen["vorgang_id"]
    if "partner_id" in aenderungen:
        if aenderungen["partner_id"] is not None:
            _nur_typ(a.typ, "schritt", "Ein Fremdgewerk kann nur einem Arbeitsschritt zugeordnet werden")
            await _pruefe_partner(session, aenderungen["partner_id"])
        a.partner_id = aenderungen["partner_id"]
    if "bestellung_id" in aenderungen:
        neue_bestellung = aenderungen["bestellung_id"]
        if neue_bestellung is not None:
            _nur_typ(a.typ, "meilenstein", "Eine Bestellung kann nur mit einem Meilenstein verknüpft werden")
            bestellung = await _pruefe_bestellung(session, neue_bestellung)
            if zeit:
                raise ZeitplanRegelverstoss(_MSG_DATUM_AUS_BESTELLUNG)
            zeit = {"start_am": bestellung.liefertermin, "ende_am": bestellung.liefertermin}
        a.bestellung_id = neue_bestellung
    elif zeit and await _aktive_bestellung(session, a.bestellung_id) is not None:
        raise ZeitplanRegelverstoss(_MSG_DATUM_AUS_BESTELLUNG)
    # Beide Phasen-Spannen (alte und neue) muessen auch ohne Datums-Aenderung
    # nachgezogen werden -- aendere_element() erledigt das nur bei Datumsfeldern.
    modus = await _projekt_modus(session, projekt)
    if zeit:
        fest = await _feste_ids(session, orm)
        aendere_element(plan, _kanten_aus(deps), modus, element_id, fest=fest, **zeit)
    else:
        aktualisiere_phasenspannen(plan)
    _schreibe_zurueck(orm, plan)
    await session.flush()


async def element_loeschen(session: AsyncSession, projekt: Projekt, element_id: UUID, user_id: UUID) -> None:
    from app.services import papierkorb_service  # lokal: vermeidet Importzyklus-Risiko

    orm, _ = await _lade(session, projekt.id)
    if element_id not in orm:
        raise ZeitplanNichtGefunden("Element nicht gefunden")
    typ = orm[element_id].typ
    await session.execute(
        delete(ProjektAufgabeAbhaengigkeit).where(
            (ProjektAufgabeAbhaengigkeit.vorgaenger_id == element_id)
            | (ProjektAufgabeAbhaengigkeit.nachfolger_id == element_id)
        )
    )
    if typ == "phase":
        # Soft-Delete loest ON DELETE SET NULL nicht aus.
        for a in orm.values():
            if a.plan_phase_id == element_id:
                a.plan_phase_id = None
    await papierkorb_service.soft_delete(
        session, entity_typ="projekt_aufgabe", entity_id=element_id, actor_user_id=user_id
    )
    await session.flush()
    await _aktualisiere_phasen(session, projekt.id)


async def _abhaengigkeit(session: AsyncSession, projekt_id: UUID, abh_id: UUID) -> ProjektAufgabeAbhaengigkeit:
    d = await session.get(ProjektAufgabeAbhaengigkeit, abh_id)
    if d is None or d.projekt_id != projekt_id:
        raise ZeitplanNichtGefunden("Abhängigkeit nicht gefunden")
    return d


async def _wende_regel_auf_nachfolger_an(session: AsyncSession, projekt: Projekt, nachfolger_id: UUID) -> None:
    orm, deps = await _lade(session, projekt.id)
    plan = _plan_aus(orm)
    modus = await _projekt_modus(session, projekt)
    propagiere(
        plan, _kanten_aus(deps), modus, {}, erzwinge=[nachfolger_id], fest=await _feste_ids(session, orm)
    )
    aktualisiere_phasenspannen(plan)
    _schreibe_zurueck(orm, plan)
    await session.flush()


async def abhaengigkeit_anlegen(
    session: AsyncSession,
    projekt: Projekt,
    *,
    mandant_id: UUID,
    user_id: UUID,
    vorgaenger_id: UUID,
    nachfolger_id: UUID,
    versatz_tage: int,
    art: str = "ende_anfang",
) -> None:
    if art not in PROJEKT_ABHAENGIGKEIT_ARTEN:
        raise ZeitplanRegelverstoss("Unbekannte Abhängigkeitsart")
    if vorgaenger_id == nachfolger_id:
        raise ZeitplanRegelverstoss("Ein Element kann nicht von sich selbst abhängen")
    orm, deps = await _lade(session, projekt.id)
    for rolle, i in (("Vorgänger", vorgaenger_id), ("Nachfolger", nachfolger_id)):
        el = orm.get(i)
        if el is None:
            raise ZeitplanRegelverstoss(f"{rolle} nicht gefunden oder gehört nicht zu diesem Projekt")
        if el.typ == "phase":
            raise ZeitplanRegelverstoss("Phasen können keine Verbindungen haben")
        if el.start_am is None or el.ende_am is None:
            raise ZeitplanRegelverstoss(f"{rolle} hat noch kein Datum -- erst terminieren")
    if any(d.vorgaenger_id == vorgaenger_id and d.nachfolger_id == nachfolger_id for d in deps):
        raise ZeitplanDuplikat("Diese Verbindung existiert bereits")
    if wuerde_zyklus_erzeugen(_kanten_aus(deps), vorgaenger_id, nachfolger_id):
        raise ZeitplanZyklus("Diese Verbindung würde einen Kreis erzeugen")
    session.add(
        ProjektAufgabeAbhaengigkeit(
            mandant_id=mandant_id,
            projekt_id=projekt.id,
            vorgaenger_id=vorgaenger_id,
            nachfolger_id=nachfolger_id,
            art=art,
            versatz_tage=versatz_tage,
            erstellt_von=user_id,
        )
    )
    await session.flush()
    await _wende_regel_auf_nachfolger_an(session, projekt, nachfolger_id)


async def abhaengigkeit_aendern(
    session: AsyncSession,
    projekt: Projekt,
    abh_id: UUID,
    versatz_tage: int | None = None,
    art: str | None = None,
) -> None:
    d = await _abhaengigkeit(session, projekt.id, abh_id)
    if art is not None:
        if art not in PROJEKT_ABHAENGIGKEIT_ARTEN:
            raise ZeitplanRegelverstoss("Unbekannte Abhängigkeitsart")
        d.art = art
    if versatz_tage is not None:
        d.versatz_tage = versatz_tage
    await session.flush()
    await _wende_regel_auf_nachfolger_an(session, projekt, d.nachfolger_id)


async def abhaengigkeit_loeschen(session: AsyncSession, projekt: Projekt, abh_id: UUID) -> None:
    d = await _abhaengigkeit(session, projekt.id, abh_id)
    await session.delete(d)
    await session.flush()


async def modus_setzen(session: AsyncSession, projekt: Projekt, modus: str) -> None:
    if modus not in VERSCHIEBE_MODI:
        raise ZeitplanRegelverstoss("Unbekannter Verschiebe-Modus")
    projekt.verschiebe_modus = modus
    await session.flush()


async def liefertermin_uebernehmen(session: AsyncSession, bestellung: Bestellung) -> None:
    """Setzt alle mit der Bestellung verknuepften Meilensteine auf deren
    (neuen) Liefertermin -- None = Meilenstein ohne Datum -- und zieht die
    Nachfolger je nach Modus des jeweiligen Projekts nach."""
    zeilen = (
        await session.execute(
            select(ProjektAufgabe.id, ProjektAufgabe.projekt_id).where(
                ProjektAufgabe.bestellung_id == bestellung.id,
                ProjektAufgabe.typ == "meilenstein",
                ProjektAufgabe.projekt_id.is_not(None),
                ProjektAufgabe.geloescht_am.is_(None),
            )
        )
    ).all()
    for element_id, projekt_id in zeilen:
        projekt = await session.get(Projekt, projekt_id)
        if projekt is None or projekt.geloescht_am is not None:
            continue
        orm, deps = await _lade(session, projekt_id)
        if element_id not in orm:
            continue
        plan = _plan_aus(orm)
        aendere_element(
            plan,
            _kanten_aus(deps),
            await _projekt_modus(session, projekt),
            element_id,
            start_am=bestellung.liefertermin,
            ende_am=bestellung.liefertermin,
            fest=await _feste_ids(session, orm),
        )
        _schreibe_zurueck(orm, plan)
        await session.flush()


# --------------------------------------------------------------------------
# Basisplan (Soll/Ist)
# --------------------------------------------------------------------------


async def _basisplan(session: AsyncSession, projekt_id: UUID, basisplan_id: UUID) -> ProjektBasisplan:
    b = await session.get(ProjektBasisplan, basisplan_id)
    if b is None or b.projekt_id != projekt_id:
        raise ZeitplanNichtGefunden("Basisplan nicht gefunden")
    return b


async def basisplan_erstellen(
    session: AsyncSession, projekt: Projekt, *, mandant_id: UUID, user_id: UUID, name: str
) -> ZeitplanBasisplanRead:
    name = name.strip()
    if not name:
        raise ZeitplanRegelverstoss("Name darf nicht leer sein")
    orm, _ = await _lade(session, projekt.id)
    basisplan = ProjektBasisplan(mandant_id=mandant_id, projekt_id=projekt.id, name=name, erstellt_von=user_id)
    session.add(basisplan)
    await session.flush()
    datiert = [a for a in orm.values() if a.start_am is not None and a.ende_am is not None]
    session.add_all(
        ProjektBasisplanEintrag(
            mandant_id=mandant_id,
            basisplan_id=basisplan.id,
            element_id=a.id,
            start_am=a.start_am,
            ende_am=a.ende_am,
        )
        for a in datiert
    )
    await session.flush()
    await session.refresh(basisplan, attribute_names=["created_at"])
    ersteller = await session.get(User, user_id)
    return ZeitplanBasisplanRead(
        id=basisplan.id,
        name=basisplan.name,
        erstellt_am=basisplan.created_at,
        erstellt_von_name=ersteller.name if ersteller else None,
        anzahl_elemente=len(datiert),
    )


async def basisplaene_lesen(session: AsyncSession, projekt: Projekt) -> list[ZeitplanBasisplanRead]:
    anzahl = (
        select(ProjektBasisplanEintrag.basisplan_id, func.count().label("n"))
        .group_by(ProjektBasisplanEintrag.basisplan_id)
        .subquery()
    )
    zeilen = (
        await session.execute(
            select(
                ProjektBasisplan.id,
                ProjektBasisplan.name,
                ProjektBasisplan.created_at,
                User.name,
                func.coalesce(anzahl.c.n, 0),
            )
            .outerjoin(User, User.id == ProjektBasisplan.erstellt_von)
            .outerjoin(anzahl, anzahl.c.basisplan_id == ProjektBasisplan.id)
            .where(ProjektBasisplan.projekt_id == projekt.id)
            .order_by(ProjektBasisplan.created_at.desc(), ProjektBasisplan.id)
        )
    ).all()
    return [
        ZeitplanBasisplanRead(id=r[0], name=r[1], erstellt_am=r[2], erstellt_von_name=r[3], anzahl_elemente=r[4])
        for r in zeilen
    ]


async def basisplan_loeschen(session: AsyncSession, projekt: Projekt, basisplan_id: UUID) -> None:
    await session.delete(await _basisplan(session, projekt.id, basisplan_id))
    await session.flush()


# --------------------------------------------------------------------------
# Plan straffen
# --------------------------------------------------------------------------


async def straffen(
    session: AsyncSession, projekt: Projekt, phase_id: UUID | None, vorschau: bool
) -> list[ZeitplanAenderung]:
    orm, deps = await _lade(session, projekt.id)
    _pruefe_phase(orm, phase_id)
    plan = _plan_aus(orm)
    geaendert = straffe_plan(plan, _kanten_aus(deps), await _feste_ids(session, orm), phase_id)
    aenderungen = [
        ZeitplanAenderung(
            element_id=i,
            titel=orm[i].titel,
            alt_start_am=orm[i].start_am,  # type: ignore[arg-type]
            alt_ende_am=orm[i].ende_am,  # type: ignore[arg-type]
            neu_start_am=plan[i].start_am,  # type: ignore[arg-type]
            neu_ende_am=plan[i].ende_am,  # type: ignore[arg-type]
        )
        for i in sorted(geaendert, key=lambda i: (plan[i].start_am, orm[i].titel, i))
    ]
    if not vorschau:
        _schreibe_zurueck(orm, plan)
        await session.flush()
    return aenderungen


# --------------------------------------------------------------------------
# Projektvorlagen
# --------------------------------------------------------------------------


async def _vorlage(session: AsyncSession, vorlage_id: UUID) -> ProjektVorlage:
    # RLS blendet fremde Mandanten aus -> hier "nicht gefunden".
    v = await session.get(ProjektVorlage, vorlage_id)
    if v is None:
        raise ZeitplanNichtGefunden("Vorlage nicht gefunden")
    return v


def _vorlage_kennzahlen(elemente: Iterable[ProjektVorlageElement]) -> tuple[int, int]:
    """(Anzahl Elemente, Gesamtspanne in Tagen)."""
    el = list(elemente)
    if not el:
        return 0, 0
    return len(el), max(e.offset_tage + e.dauer_tage for e in el) - min(e.offset_tage for e in el)


async def vorlagen_lesen(session: AsyncSession) -> list[ProjektVorlageListe]:
    vorlagen = (
        await session.execute(select(ProjektVorlage).order_by(func.lower(ProjektVorlage.name), ProjektVorlage.id))
    ).scalars().all()
    elemente: dict[UUID, list[ProjektVorlageElement]] = defaultdict(list)
    for e in (await session.execute(select(ProjektVorlageElement))).scalars():
        elemente[e.vorlage_id].append(e)
    out = []
    for v in vorlagen:
        anzahl, dauer = _vorlage_kennzahlen(elemente[v.id])
        out.append(
            ProjektVorlageListe(
                id=v.id, name=v.name, beschreibung=v.beschreibung, anzahl_elemente=anzahl, dauer_tage=dauer
            )
        )
    return out


async def vorlage_detail(session: AsyncSession, vorlage_id: UUID) -> ProjektVorlageDetail:
    v = await _vorlage(session, vorlage_id)
    elemente = (
        await session.execute(
            select(ProjektVorlageElement)
            .where(ProjektVorlageElement.vorlage_id == v.id)
            .order_by(ProjektVorlageElement.typ != "phase", ProjektVorlageElement.reihenfolge, ProjektVorlageElement.ref)
        )
    ).scalars().all()
    deps = (
        await session.execute(
            select(ProjektVorlageAbhaengigkeit)
            .where(ProjektVorlageAbhaengigkeit.vorlage_id == v.id)
            .order_by(ProjektVorlageAbhaengigkeit.vorgaenger_ref, ProjektVorlageAbhaengigkeit.nachfolger_ref)
        )
    ).scalars().all()
    anzahl, dauer = _vorlage_kennzahlen(elemente)
    return ProjektVorlageDetail(
        id=v.id,
        name=v.name,
        beschreibung=v.beschreibung,
        anzahl_elemente=anzahl,
        dauer_tage=dauer,
        elemente=[
            ProjektVorlageElementRead(
                ref=e.ref,
                typ=e.typ,  # type: ignore[arg-type]
                titel=e.titel,
                phase_ref=e.phase_ref,
                offset_tage=e.offset_tage,
                dauer_tage=e.dauer_tage,
                reihenfolge=e.reihenfolge,
            )
            for e in elemente
        ],
        abhaengigkeiten=[
            ProjektVorlageAbhaengigkeitRead(
                vorgaenger_ref=d.vorgaenger_ref,
                nachfolger_ref=d.nachfolger_ref,
                art=d.art,  # type: ignore[arg-type]
                versatz_tage=d.versatz_tage,
            )
            for d in deps
        ],
    )


async def vorlage_aus_projekt(
    session: AsyncSession,
    projekt: Projekt,
    *,
    mandant_id: UUID,
    user_id: UUID,
    name: str,
    beschreibung: str | None,
) -> UUID:
    """Uebernimmt Struktur und Dauern des aktuellen Zeitplans. Offsets sind
    relativ zum fruehesten Start. Elemente ohne Datum und Phasen ohne
    datierte Elemente werden weggelassen (ein Offset waere erfunden), samt
    ihrer Verbindungen. Vorgang/Bestellung/Partner/Zustaendige werden nicht
    uebernommen -- ein Liefer-Meilenstein wird zum normalen Meilenstein."""
    name = name.strip()
    if not name:
        raise ZeitplanRegelverstoss("Name darf nicht leer sein")
    orm, deps = await _lade(session, projekt.id)
    datiert = [a for a in orm.values() if a.typ != "phase" and a.start_am is not None and a.ende_am is not None]
    if not datiert:
        raise ZeitplanRegelverstoss("Der Zeitplan hat keine terminierten Elemente für eine Vorlage")
    null = min(a.start_am for a in datiert)  # type: ignore[type-var]
    phasen_mit_kindern = {a.plan_phase_id for a in datiert if a.plan_phase_id is not None}
    uebernommen = [a for a in orm.values() if a in datiert or (a.typ == "phase" and a.id in phasen_mit_kindern)]
    refs: dict[UUID, str] = {}
    for a in sorted(uebernommen, key=lambda a: (a.typ != "phase", a.plan_reihenfolge, a.created_at)):
        refs[a.id] = f"{a.typ[0]}{len(refs) + 1}"

    vorlage = ProjektVorlage(
        mandant_id=mandant_id, name=name, beschreibung=(beschreibung or "").strip() or None, erstellt_von=user_id
    )
    session.add(vorlage)
    await session.flush()
    for a in uebernommen:
        if a.typ == "phase":
            kinder = [k for k in datiert if k.plan_phase_id == a.id]
            start = min(k.start_am for k in kinder)  # type: ignore[type-var]
            ende = max(k.ende_am for k in kinder)  # type: ignore[type-var]
        else:
            start, ende = a.start_am, a.ende_am
        session.add(
            ProjektVorlageElement(
                mandant_id=mandant_id,
                vorlage_id=vorlage.id,
                ref=refs[a.id],
                typ=a.typ,
                titel=a.titel,
                phase_ref=refs.get(a.plan_phase_id) if a.typ != "phase" and a.plan_phase_id else None,
                offset_tage=(start - null).days,  # type: ignore[operator]
                dauer_tage=1 if a.typ == "meilenstein" else (ende - start).days + 1,  # type: ignore[operator]
                reihenfolge=a.plan_reihenfolge,
            )
        )
    for d in deps:
        if d.vorgaenger_id in refs and d.nachfolger_id in refs:
            session.add(
                ProjektVorlageAbhaengigkeit(
                    mandant_id=mandant_id,
                    vorlage_id=vorlage.id,
                    vorgaenger_ref=refs[d.vorgaenger_id],
                    nachfolger_ref=refs[d.nachfolger_id],
                    art=d.art,
                    versatz_tage=d.versatz_tage,
                )
            )
    await session.flush()
    return vorlage.id


async def vorlage_aendern(session: AsyncSession, vorlage_id: UUID, aenderungen: Mapping[str, Any]) -> None:
    v = await _vorlage(session, vorlage_id)
    if "name" in aenderungen:
        if aenderungen["name"] is None or not aenderungen["name"].strip():
            raise ZeitplanRegelverstoss("Name darf nicht leer sein")
        v.name = aenderungen["name"].strip()
    if "beschreibung" in aenderungen:
        v.beschreibung = (aenderungen["beschreibung"] or "").strip() or None
    await session.flush()


async def vorlage_loeschen(session: AsyncSession, vorlage_id: UUID) -> None:
    await session.delete(await _vorlage(session, vorlage_id))
    await session.flush()


async def vorlage_anwenden(
    session: AsyncSession,
    projekt: Projekt,
    *,
    mandant_id: UUID,
    user_id: UUID,
    vorlage_id: UUID,
    start_am: date,
) -> None:
    """Haengt die Vorlage an den bestehenden Plan an (Reihenfolge hinten).
    Die Termine ergeben sich allein aus Offset/Dauer -- es wird bewusst
    nicht propagiert, damit Struktur und Abstaende exakt der Vorlage
    entsprechen."""
    vorlage = await _vorlage(session, vorlage_id)
    elemente = sorted(
        (
            await session.execute(
                select(ProjektVorlageElement).where(ProjektVorlageElement.vorlage_id == vorlage.id)
            )
        ).scalars(),
        key=lambda e: (e.reihenfolge, e.ref),
    )
    deps = (
        await session.execute(
            select(ProjektVorlageAbhaengigkeit).where(ProjektVorlageAbhaengigkeit.vorlage_id == vorlage.id)
        )
    ).scalars().all()
    orm, _ = await _lade(session, projekt.id)
    spalte_id = (
        await session.execute(
            select(ProjektSpalte.id)
            .where(ProjektSpalte.projekt_id == projekt.id)
            .order_by(ProjektSpalte.reihenfolge)
            .limit(1)
        )
    ).scalar_one_or_none()

    ids = {e.ref: uuid.uuid4() for e in elemente}
    phasen_refs = {e.ref for e in elemente if e.typ == "phase"}
    zaehler: dict[UUID | None | str, int] = {
        "phase": _naechste_reihenfolge(orm, "phase", None),
        None: _naechste_reihenfolge(orm, "schritt", None),
    }
    for e in sorted(elemente, key=lambda e: e.typ != "phase"):
        if e.typ == "phase":
            gruppe: UUID | None | str = "phase"
            start = ende = None
            phase_id = None
        else:
            phase_id = ids[e.phase_ref] if e.phase_ref in phasen_refs else None
            gruppe = phase_id
            start = start_am + timedelta(days=e.offset_tage)
            ende = start if e.typ == "meilenstein" else start + timedelta(days=e.dauer_tage - 1)
        nummer = zaehler.get(gruppe, 0)
        zaehler[gruppe] = nummer + 1
        session.add(
            ProjektAufgabe(
                id=ids[e.ref],
                mandant_id=mandant_id,
                projekt_id=projekt.id,
                spalte_id=spalte_id if e.typ == "schritt" else None,
                typ=e.typ,
                titel=e.titel,
                start_am=start,
                ende_am=ende,
                plan_phase_id=phase_id,
                plan_reihenfolge=nummer,
                erstellt_von=user_id,
            )
        )
    await session.flush()
    for d in deps:
        if d.vorgaenger_ref in ids and d.nachfolger_ref in ids:
            session.add(
                ProjektAufgabeAbhaengigkeit(
                    mandant_id=mandant_id,
                    projekt_id=projekt.id,
                    vorgaenger_id=ids[d.vorgaenger_ref],
                    nachfolger_id=ids[d.nachfolger_ref],
                    art=d.art,
                    versatz_tage=d.versatz_tage,
                    erstellt_von=user_id,
                )
            )
    await session.flush()
    await _aktualisiere_phasen(session, projekt.id)


def _like_muster(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def auswahl_vorgaenge(
    session: AsyncSession,
    projekt: Projekt,
    q: str | None,
    limit: int,
    erlaubte_kunden: set[UUID] | None,
) -> list[ZeitplanVorgangAuswahl]:
    """Vorgaenge des Projekts (direkt oder ueber einen Auftrag des Projekts)
    zuerst, danach die uebrigen des Mandanten."""
    gehoert = or_(Vorgang.projekt_id == projekt.id, Auftrag.projekt_id == projekt.id)
    stmt = (
        select(Vorgang.id, Vorgang.vorgangsnummer, Vorgang.titel, Vorgang.status, gehoert.label("gehoert"))
        .outerjoin(Auftrag, Auftrag.id == Vorgang.auftrag_id)
        .where(Vorgang.geloescht_am.is_(None))
    )
    if erlaubte_kunden is not None:
        stmt = stmt.where(Vorgang.kunde_id.in_(erlaubte_kunden))
    if q and q.strip():
        muster = _like_muster(q.strip())
        stmt = stmt.where(or_(Vorgang.vorgangsnummer.ilike(muster), Vorgang.titel.ilike(muster)))
    stmt = stmt.order_by(func.coalesce(gehoert, False).desc(), Vorgang.created_at.desc()).limit(limit)
    return [
        ZeitplanVorgangAuswahl(
            id=r[0], vorgangsnummer=r[1], titel=r[2], status=r[3], gehoert_zum_projekt=bool(r[4])
        )
        for r in (await session.execute(stmt)).all()
    ]


async def auswahl_bestellungen(
    session: AsyncSession, q: str | None, limit: int
) -> list[ZeitplanBestellungAuswahl]:
    stmt = (
        select(Bestellung.id, Bestellung.bestellnummer, Bestellung.status, Bestellung.liefertermin, Lieferant.name)
        .outerjoin(Lieferant, Lieferant.id == Bestellung.lieferant_id)
        .where(Bestellung.geloescht_am.is_(None))
    )
    if q and q.strip():
        muster = _like_muster(q.strip())
        stmt = stmt.where(or_(Bestellung.bestellnummer.ilike(muster), Lieferant.name.ilike(muster)))
    stmt = stmt.order_by(Bestellung.created_at.desc()).limit(limit)
    return [
        ZeitplanBestellungAuswahl(id=r[0], bestellnummer=r[1], status=r[2], liefertermin=r[3], lieferant_name=r[4])
        for r in (await session.execute(stmt)).all()
    ]
