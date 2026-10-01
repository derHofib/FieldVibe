"""Gantt-Zeitplan fuer Projekte: Phasen, Arbeitsschritte, Meilensteine mit
Ende->Anfang-Abhaengigkeiten.

Zweigeteilt: der obere Teil (PlanElement, propagiere, aendere_element, ...)
rechnet rein auf In-Memory-Strukturen und kennt weder Datenbank noch HTTP --
dort liegt die gesamte Terminlogik und ist entsprechend direkt testbar. Der
untere Teil (lade/schreibe, element_*/abhaengigkeit_*) ist die duenne
DB-Schicht darum herum.

Gerechnet wird in Kalendertagen, Datumsbereiche sind inklusiv
(start_am..ende_am).
"""
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Iterable, Mapping
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.projekt import (
    Projekt,
    ProjektAufgabe,
    ProjektAufgabeAbhaengigkeit,
    ProjektSpalte,
)
from app.models.user import User
from app.schemas.projekt import ZeitplanAbhaengigkeit, ZeitplanElement, ZeitplanRead

ZEITPLAN_TYPEN = ("phase", "schritt", "meilenstein")
VERSCHIEBE_MODI = ("bei_konflikt", "immer")

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
) -> set[UUID]:
    """Zieht alle transitiven Nachfolger der `ausgangspunkte` nach.

    `ausgangspunkte` bildet die bereits (vom Aufrufer) geaenderten Elemente
    auf die Aenderung ihres Endes in Tagen ab (positiv = spaeter). Sie selbst
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
      nach vorne also das kleinste Stueck nach vorne -- vorsichtig).
    * Beide Modi: danach wird die Konflikt-Regel durchgesetzt. N darf keinen
      Vorgaenger verletzen: ist N.start < fruehester Start (Maximum ueber
      ALLE Vorgaenger, auch unbewegte), wird N um genau die Differenz nach
      hinten geschoben. Die Dauer bleibt immer erhalten.
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
    verschoben: set[UUID] = set()
    for n in reihenfolge:
        if n in ausgangspunkte:
            continue
        el = elemente[n]
        alt_ende = el.ende_am
        eingehend = vorgaenger_von[n]

        if modus == "immer":
            deltas = [ende_delta[k.vorgaenger_id] for k in eingehend if k.vorgaenger_id in ende_delta]
            if deltas:
                _verschiebe(el, max(deltas))

        if eingehend:
            frueh = max(fruehester_start(elemente[k.vorgaenger_id], k.versatz_tage) for k in eingehend)
            assert el.start_am is not None
            if el.start_am < frueh:
                _verschiebe(el, (frueh - el.start_am).days)

        assert el.ende_am is not None and alt_ende is not None
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


def verschiebe_phase(elemente: dict[UUID, PlanElement], phase_id: UUID, tage: int) -> dict[UUID, int]:
    """Verschiebt alle Elemente mit Datum der Phase um `tage`. Rueckgabe: die
    bewegten Elemente mit ihrem Ende-Delta (= `tage`), als `ausgangspunkte`
    fuer propagiere() geeignet."""
    bewegt: dict[UUID, int] = {}
    for el in elemente.values():
        if el.typ != "phase" and el.phase_id == phase_id and _datiert(el):
            _verschiebe(el, tage)
            bewegt[el.id] = tage
    return bewegt


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
        ausgangspunkte = verschiebe_phase(elemente, element_id, delta_start)
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
        elif neu_ende is not None:
            # Erstmals datiert: kein Delta, aber Nachfolger (falls
            # Verbindungen existieren) gegen das neue Ende pruefen.
            ausgangspunkte = {element_id: 0}
        else:
            ausgangspunkte = {}

    if ausgangspunkte:
        propagiere(elemente, kanten, modus, ausgangspunkte)
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
    return [PlanKante(d.vorgaenger_id, d.nachfolger_id, d.versatz_tage) for d in deps]


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


async def lese_zeitplan(session: AsyncSession, projekt: Projekt) -> ZeitplanRead:
    modus = await _projekt_modus(session, projekt)
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
    elemente = [
        ZeitplanElement(
            id=r[0],
            typ=r[1],
            titel=r[2],
            phase_id=r[3],
            start_am=r[4],
            ende_am=r[5],
            fortschritt=r[6],
            plan_reihenfolge=r[7],
            zugewiesen_an=r[8],
            zugewiesen_name=r[9],
            erledigt=r[10] is not None,
        )
        for r in zeilen
    ]
    # Phasen zuerst (nach plan_reihenfolge), danach die Elemente -- das
    # Frontend gruppiert selbst anhand phase_id.
    elemente.sort(key=lambda e: (e.typ != "phase", e.plan_reihenfolge))
    ids = {e.id for e in elemente}
    deps = (
        await session.execute(
            select(ProjektAufgabeAbhaengigkeit)
            .where(ProjektAufgabeAbhaengigkeit.projekt_id == projekt.id)
            .order_by(ProjektAufgabeAbhaengigkeit.created_at)
        )
    ).scalars()
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
            )
            for d in deps
            if d.vorgaenger_id in ids and d.nachfolger_id in ids
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
    session: AsyncSession, projekt: Projekt, element_id: UUID, aenderungen: Mapping[str, Any], mandant_id: UUID
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
    # Beide Phasen-Spannen (alte und neue) muessen auch ohne Datums-Aenderung
    # nachgezogen werden -- aendere_element() erledigt das nur bei Datumsfeldern.
    modus = await _projekt_modus(session, projekt)
    if zeit:
        aendere_element(plan, _kanten_aus(deps), modus, element_id, **zeit)
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
    propagiere(plan, _kanten_aus(deps), modus, {}, erzwinge=[nachfolger_id])
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
) -> None:
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
            art="ende_anfang",
            versatz_tage=versatz_tage,
            erstellt_von=user_id,
        )
    )
    await session.flush()
    await _wende_regel_auf_nachfolger_an(session, projekt, nachfolger_id)


async def abhaengigkeit_aendern(
    session: AsyncSession, projekt: Projekt, abh_id: UUID, versatz_tage: int
) -> None:
    d = await _abhaengigkeit(session, projekt.id, abh_id)
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
