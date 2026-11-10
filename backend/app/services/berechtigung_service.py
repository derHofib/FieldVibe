"""Zentrale Rechte-Engine (docs/konzepte/ORGANIGRAMM.md): einzige Stelle, die
effektive Rechte aufloest. require_recht, /api/auth/me und die Scope-Helfer
laufen ausschliesslich hierueber; rechte_service bleibt fuer die
Account-Typ-Verwaltung (Matrix je Typ) zustaendig.

Aufloesung fuer role='custom':
  1. aktive Besetzungen (Fenster gueltig_von <= Stichtag < gueltig_bis; Vertretung
     wie regulaer), Position nicht archiviert und im Gueltigkeitsfenster
  2. je Position: Account-Typ-Basis (erlaubt=true) + Positions-Overrides
     (erlauben fuegt hinzu/erweitert den Scope, verweigern entfernt nur den
     Beitrag dieser Position)
  3. Vereinigung ueber Positionen: je (bereich, aktion) gewinnt der groesste Scope
  4. User-Overrides: erlauben fuegt hinzu/erweitert, verweigern gilt global
Ohne aktive Besetzung gibt es keine Rechte (Platzhalter = Vorlage).
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rechte_registry import SCOPE_RANG, alle_bereiche
from app.models.account_typ import AccountTyp, AccountTypRecht
from app.models.organigramm import OrgEinheit, Position, PositionBesetzung, PositionRecht, UserRecht

_CACHE_KEY = "berechtigung_cache"

# Typ-Flags (kein Teil der (bereich, aktion)-Matrix), ueber die aktiven Positionen vereinigt.
FLAG_SELBST_UEBERNEHMEN = "darf_vorgaenge_selbst_uebernehmen"
FLAG_ZEITEN_BUCHEN = "darf_zeiten_buchen"
FLAG_ABWESENHEITEN_VERWALTEN = "darf_abwesenheiten_verwalten"
_FLAGS = (FLAG_SELBST_UEBERNEHMEN, FLAG_ZEITEN_BUCHEN, FLAG_ABWESENHEITEN_VERWALTEN)

Herkunft = dict[str, Any]
RechtKey = tuple[str, str]


@dataclass(frozen=True)
class Recht:
    bereich: str
    aktion: str
    scope: str
    herkunft: tuple[Herkunft, ...]


@dataclass
class EffektiveRechte:
    user_id: UUID
    rolle: str
    rechte: dict[RechtKey, Recht] = field(default_factory=dict)
    # Je Recht die gewaehrenden Positionen mit ihrem jeweiligen Scope -- der Scope
    # wird relativ zu jeder dieser Positionen aufgeloest (user_ids_fuer_recht).
    gewaehrende_positionen: dict[RechtKey, dict[UUID, str]] = field(default_factory=dict)
    # Verweigerungen (Position oder User) fuer die spaetere Matrix-Herkunftsanzeige.
    verweigert: dict[RechtKey, list[Herkunft]] = field(default_factory=dict)
    aktive_position_ids: tuple[UUID, ...] = ()
    # Positionen mit Account-Typ -> Typ (fuer die Flag-Aufloesung).
    typ_je_position: dict[UUID, AccountTyp] = field(default_factory=dict)
    alle_rechte: bool = False

    def hat(self, bereich: str, aktion: str) -> bool:
        return self.alle_rechte or (bereich, aktion) in self.rechte

    def scope(self, bereich: str, aktion: str) -> str | None:
        if self.alle_rechte:
            return "mandant"
        recht = self.rechte.get((bereich, aktion))
        return recht.scope if recht else None

    def flag(self, name: str) -> bool:
        if self.alle_rechte:
            return True
        return any(getattr(t, name) for t in self.typ_je_position.values())

    @property
    def alle_typen_nur_zugewiesene_kunden(self) -> bool:
        typen = self.typ_je_position.values()
        return bool(typen) and all(t.nur_zugewiesene_kunden for t in typen)

    def als_matrix(self) -> dict[str, list[str]]:
        """Bereich -> erlaubte Aktionen (Form von /api/auth/me.rechte)."""
        return {
            b.key: [a for a in b.aktionen if self.hat(b.key, a)] for b in alle_bereiche()
        }

    def als_scopes(self) -> dict[str, dict[str, str]]:
        ergebnis: dict[str, dict[str, str]] = {}
        for b in alle_bereiche():
            je_aktion = {a: s for a in b.aktionen if (s := self.scope(b.key, a)) is not None}
            if je_aktion:
                ergebnis[b.key] = je_aktion
        return ergebnis


def _jetzt(stichtag: datetime | None) -> datetime:
    return stichtag or datetime.now(timezone.utc)


def _groesser(a: str | None, b: str) -> str:
    return b if a is None or SCOPE_RANG[b] > SCOPE_RANG[a] else a


async def effektive_rechte(
    session: AsyncSession, *, user_id: UUID, rolle: str, stichtag: datetime | None = None
) -> EffektiveRechte:
    """Aufloesung ohne Cache (siehe hat_recht/scope_von fuer den Request-Cache)."""
    ergebnis = EffektiveRechte(user_id=user_id, rolle=rolle)

    if rolle != "custom":
        # super_admin, mandant_admin, loesch_operativ, loesch_ansicht: alle
        # Registry-Rechte mit Scope mandant, wie vor der Engine.
        ergebnis.alle_rechte = True
        for b in alle_bereiche():
            for aktion in b.aktionen:
                key = (b.key, aktion)
                ergebnis.rechte[key] = Recht(b.key, aktion, "mandant", ({"art": "rolle", "rolle": rolle},))
        return ergebnis

    jetzt = _jetzt(stichtag)
    heute = jetzt.date()
    besetzungen = (
        await session.execute(
            select(PositionBesetzung, Position)
            .join(Position, Position.id == PositionBesetzung.position_id)
            .where(
                PositionBesetzung.user_id == user_id,
                PositionBesetzung.gueltig_von <= jetzt,
                or_(PositionBesetzung.gueltig_bis.is_(None), PositionBesetzung.gueltig_bis > jetzt),
                or_(Position.archiviert_am.is_(None), Position.archiviert_am > jetzt),
                or_(Position.gueltig_ab.is_(None), Position.gueltig_ab <= heute),
                or_(Position.gueltig_bis.is_(None), Position.gueltig_bis >= heute),
            )
        )
    ).all()

    positionen: dict[UUID, Position] = {}
    arten: dict[UUID, set[str]] = defaultdict(set)
    for besetzung, position in besetzungen:
        positionen[position.id] = position
        arten[position.id].add(besetzung.art)
    ergebnis.aktive_position_ids = tuple(positionen)
    if not positionen:
        # Auch User-Overrides wirken nicht ohne Besetzung.
        return ergebnis

    # position_id -> {key: (scope, [herkunft])}: Beitrag je Position nach Basis + Override.
    je_position: dict[UUID, dict[RechtKey, tuple[str, list[Herkunft]]]] = {}
    typ_ids = {p.account_typ_id for p in positionen.values() if p.account_typ_id is not None}
    typen: dict[UUID, AccountTyp] = {}
    basis: dict[UUID, list[AccountTypRecht]] = defaultdict(list)
    if typ_ids:
        typen = {
            t.id: t
            for t in (await session.execute(select(AccountTyp).where(AccountTyp.id.in_(typ_ids))))
            .scalars()
            .all()
        }
        for r in (
            await session.execute(
                select(AccountTypRecht).where(
                    AccountTypRecht.account_typ_id.in_(typ_ids), AccountTypRecht.erlaubt.is_(True)
                )
            )
        ).scalars():
            basis[r.account_typ_id].append(r)
    overrides: dict[UUID, list[PositionRecht]] = defaultdict(list)
    for o in (
        await session.execute(select(PositionRecht).where(PositionRecht.position_id.in_(positionen)))
    ).scalars():
        overrides[o.position_id].append(o)

    for pid, position in positionen.items():
        beitrag: dict[RechtKey, tuple[str, list[Herkunft]]] = {}
        if position.account_typ_id is not None and position.account_typ_id in typen:
            ergebnis.typ_je_position[pid] = typen[position.account_typ_id]
            for r in basis.get(position.account_typ_id, []):
                beitrag[(r.bereich, r.aktion)] = (
                    r.scope,
                    [
                        {
                            "art": "account_typ",
                            "position_id": str(pid),
                            "account_typ_id": str(position.account_typ_id),
                        }
                    ],
                )
        for o in overrides.get(pid, []):
            key = (o.bereich, o.aktion)
            herkunft = {"art": "position_override", "position_id": str(pid), "wirkung": o.wirkung}
            if o.wirkung == "verweigern":
                beitrag.pop(key, None)
                ergebnis.verweigert.setdefault(key, []).append(herkunft)
                continue
            # scope=None beim Erlauben: bestehenden Basis-Scope behalten, sonst mandant
            # (gleicher Default wie account_typ_rechte.scope).
            alt = beitrag.get(key)
            scope = o.scope or (alt[0] if alt else "mandant")
            if alt is not None:
                scope = _groesser(alt[0], scope)
            beitrag[key] = (scope, (alt[1] if alt else []) + [herkunft])
        je_position[pid] = beitrag

    gesammelt: dict[RechtKey, tuple[str, list[Herkunft]]] = {}
    gewaehrend: dict[RechtKey, dict[UUID, str]] = defaultdict(dict)
    for pid, beitrag in je_position.items():
        for key, (scope, herkunft) in beitrag.items():
            alt = gesammelt.get(key)
            gesammelt[key] = (_groesser(alt[0] if alt else None, scope), (alt[1] if alt else []) + herkunft)
            gewaehrend[key][pid] = scope

    user_overrides = (
        (await session.execute(select(UserRecht).where(UserRecht.user_id == user_id))).scalars().all()
    )
    for o in user_overrides:
        key = (o.bereich, o.aktion)
        herkunft = {"art": "user_override", "wirkung": o.wirkung}
        if o.wirkung == "verweigern":
            gesammelt.pop(key, None)
            gewaehrend.pop(key, None)
            ergebnis.verweigert.setdefault(key, []).append(herkunft)
            continue
        alt = gesammelt.get(key)
        scope = o.scope or (alt[0] if alt else "mandant")
        gesammelt[key] = (_groesser(alt[0] if alt else None, scope), (alt[1] if alt else []) + [herkunft])
        # Ohne eigene Position: Scope relativ zu allen aktiven Positionen des Users.
        for pid in positionen:
            gewaehrend[key][pid] = _groesser(gewaehrend[key].get(pid), scope)

    for (bereich, aktion), (scope, herkunft) in gesammelt.items():
        ergebnis.rechte[(bereich, aktion)] = Recht(bereich, aktion, scope, tuple(herkunft))
    ergebnis.gewaehrende_positionen = {k: dict(v) for k, v in gewaehrend.items()}
    return ergebnis


def cache_leeren(session: AsyncSession) -> None:
    """Nach Aenderungen an Besetzungen/Rechten innerhalb desselben Requests."""
    session.info.pop(_CACHE_KEY, None)


async def effektive_rechte_gecacht(
    session: AsyncSession, *, user_id: UUID, rolle: str
) -> EffektiveRechte:
    """Pro Session (= pro Request) hoechstens eine Aufloesung je Nutzer."""
    cache: dict[tuple[UUID, str], EffektiveRechte] = session.info.setdefault(_CACHE_KEY, {})
    key = (user_id, rolle)
    if key not in cache:
        cache[key] = await effektive_rechte(session, user_id=user_id, rolle=rolle)
    return cache[key]


async def hat_recht(session: AsyncSession, auth: Any, bereich: str, aktion: str) -> bool:
    """auth: alles mit user_id und role (AuthContext)."""
    rechte = await effektive_rechte_gecacht(session, user_id=auth.user_id, rolle=auth.role)
    return rechte.hat(bereich, aktion)


async def scope_von(session: AsyncSession, auth: Any, bereich: str, aktion: str) -> str | None:
    rechte = await effektive_rechte_gecacht(session, user_id=auth.user_id, rolle=auth.role)
    return rechte.scope(bereich, aktion)


async def flag_von(session: AsyncSession, *, user_id: UUID, rolle: str, flag: str) -> bool:
    if flag not in _FLAGS:
        raise ValueError(flag)
    return (await effektive_rechte_gecacht(session, user_id=user_id, rolle=rolle)).flag(flag)


async def ist_auf_zugewiesene_kunden_beschraenkt(
    session: AsyncSession, *, user_id: UUID, rolle: str
) -> bool:
    """Eingeschraenkt, wenn kunden.sehen nur mit Scope "eigene" gilt. Zusaetzlich
    (fail-safe, solange das Flag account_typen.nur_zugewiesene_kunden noch
    existiert): wenn alle Typen der aktiven Positionen das Flag tragen -- so
    kann ein nicht auf Scope umgesetztes Flag nie Rechte erweitern."""
    if rolle != "custom":
        return False
    rechte = await effektive_rechte_gecacht(session, user_id=user_id, rolle=rolle)
    if rechte.scope("kunden", "sehen") == "eigene":
        return True
    return rechte.alle_typen_nur_zugewiesene_kunden


# --- Baum-Helfer (Scope-Aufloesung, Schritt 4) -------------------------------


async def teilbaum_position_ids(session: AsyncSession, position_id: UUID) -> set[UUID]:
    return await _teilbaum_position_ids(session, [position_id])


async def _teilbaum_position_ids(session: AsyncSession, start_ids: list[UUID]) -> set[UUID]:
    """Position + alle Unterpositionen. Der Abstieg ueberspringt Kinder mit typ
    stabsstelle (samt ihrem Teilbaum): der Linien-Teilbaum laeuft nie ueber eine
    Stabsstelle hinweg. Startet man selbst an einer Stabsstelle, gehoeren alle ihre
    Unterpositionen (auch typ linie) dazu, verschachtelte Stabsstellen nicht.
    UNION (nicht ALL) beendet auch fehlerhafte Zyklen."""
    if not start_ids:
        return set()
    zeilen = await session.execute(
        text(
            """
            WITH RECURSIVE teilbaum(id) AS (
              SELECT id FROM positionen WHERE id = ANY(:start)
              UNION
              SELECT p.id FROM positionen p JOIN teilbaum t ON p.parent_id = t.id
              WHERE p.typ <> 'stabsstelle' AND p.archiviert_am IS NULL
            )
            SELECT id FROM teilbaum
            """
        ),
        {"start": list(start_ids)},
    )
    return {row[0] for row in zeilen}


async def _team_position_ids(session: AsyncSession, position_ids: list[UUID]) -> set[UUID]:
    """Team = Positionen derselben org_einheit_id; ohne Einheit dieselbe
    Elternposition (Geschwister). Die Wurzel (weder Einheit noch Eltern) ist
    nur sie selbst."""
    ergebnis: set[UUID] = set(position_ids)
    if not position_ids:
        return ergebnis
    quellen = (
        (await session.execute(select(Position).where(Position.id.in_(position_ids)))).scalars().all()
    )
    einheiten = {p.org_einheit_id for p in quellen if p.org_einheit_id is not None}
    eltern = {p.parent_id for p in quellen if p.org_einheit_id is None and p.parent_id is not None}
    bedingungen = []
    if einheiten:
        bedingungen.append(Position.org_einheit_id.in_(einheiten))
    if eltern:
        bedingungen.append(and_(Position.org_einheit_id.is_(None), Position.parent_id.in_(eltern)))
    if bedingungen:
        gefunden = await session.execute(
            select(Position.id).where(or_(*bedingungen), Position.archiviert_am.is_(None))
        )
        ergebnis |= {row[0] for row in gefunden}
    return ergebnis


async def _bereich_position_ids(session: AsyncSession, position_ids: list[UUID]) -> set[UUID]:
    """Oberste Org-Einheit vom typ bereich in der Ahnenkette der Einheit der
    Position und alle Positionen in ihr und darunter. Ohne Einheit/Bereich in
    der Kette entfaellt dieser Anteil (der Scope umfasst dann nur Teilbaum/Team)."""
    ergebnis: set[UUID] = set()
    if not position_ids:
        return ergebnis
    einheit_ids = {
        row[0]
        for row in await session.execute(
            select(Position.org_einheit_id).where(
                Position.id.in_(position_ids), Position.org_einheit_id.is_not(None)
            )
        )
    }
    if not einheit_ids:
        return ergebnis
    wurzeln: set[UUID] = set()
    for einheit_id in einheit_ids:
        # Aufwaerts laufen, die zuletzt (am weitesten oben) gefundene Bereichs-Einheit gilt.
        oberster: UUID | None = None
        aktuell: UUID | None = einheit_id
        gesehen: set[UUID] = set()
        while aktuell is not None and aktuell not in gesehen:
            gesehen.add(aktuell)
            einheit = await session.get(OrgEinheit, aktuell)
            if einheit is None:
                break
            if einheit.typ == "bereich":
                oberster = einheit.id
            aktuell = einheit.parent_id
        if oberster is not None:
            wurzeln.add(oberster)
    if not wurzeln:
        return ergebnis
    zeilen = await session.execute(
        text(
            """
            WITH RECURSIVE einheiten(id) AS (
              SELECT id FROM org_einheiten WHERE id = ANY(:start)
              UNION
              SELECT e.id FROM org_einheiten e JOIN einheiten x ON e.parent_id = x.id
            )
            SELECT p.id FROM positionen p
            WHERE p.org_einheit_id IN (SELECT id FROM einheiten) AND p.archiviert_am IS NULL
            """
        ),
        {"start": list(wurzeln)},
    )
    return {row[0] for row in zeilen}


async def _user_ids_auf_positionen(
    session: AsyncSession, position_ids: set[UUID], stichtag: datetime | None
) -> set[UUID]:
    if not position_ids:
        return set()
    jetzt = _jetzt(stichtag)
    zeilen = await session.execute(
        select(PositionBesetzung.user_id).where(
            PositionBesetzung.position_id.in_(position_ids),
            PositionBesetzung.gueltig_von <= jetzt,
            or_(PositionBesetzung.gueltig_bis.is_(None), PositionBesetzung.gueltig_bis > jetzt),
        )
    )
    return {row[0] for row in zeilen}


async def user_ids_fuer_scope(
    session: AsyncSession,
    gewaehrende_position_ids: list[UUID] | set[UUID],
    scope: str,
    *,
    user_id: UUID | None = None,
    stichtag: datetime | None = None,
) -> set[UUID] | None:
    """Nutzer, deren Daten ein Scope umfasst; None = unbeschraenkt (mandant).
    Hoehere Scopes umfassen die niedrigeren (eigene < team < teilbaum < bereich),
    der Nutzer selbst ist immer enthalten (user_id)."""
    if scope == "mandant":
        return None
    ergebnis: set[UUID] = {user_id} if user_id is not None else set()
    if scope == "eigene":
        return ergebnis
    positionen = list(gewaehrende_position_ids)
    betroffen = await _team_position_ids(session, positionen)
    if SCOPE_RANG[scope] >= SCOPE_RANG["teilbaum"]:
        betroffen |= await _teilbaum_position_ids(session, positionen)
    if SCOPE_RANG[scope] >= SCOPE_RANG["bereich"]:
        betroffen |= await _bereich_position_ids(session, positionen)
    return ergebnis | await _user_ids_auf_positionen(session, betroffen, stichtag)


async def user_ids_fuer_recht(
    session: AsyncSession, auth: Any, bereich: str, aktion: str
) -> set[UUID] | None:
    """None = unbeschraenkt; leere Menge bzw. nur der eigene User, wenn das Recht
    fehlt oder auf "eigene" begrenzt ist. Mehrere Positionen mit unterschiedlichem
    Scope werden vereinigt."""
    rechte = await effektive_rechte_gecacht(session, user_id=auth.user_id, rolle=auth.role)
    if rechte.alle_rechte:
        return None
    je_position = rechte.gewaehrende_positionen.get((bereich, aktion))
    if not je_position:
        return set()
    nach_scope: dict[str, list[UUID]] = defaultdict(list)
    for pid, scope in je_position.items():
        nach_scope[scope].append(pid)
    ergebnis: set[UUID] = set()
    for scope, pids in nach_scope.items():
        teil = await user_ids_fuer_scope(session, pids, scope, user_id=auth.user_id)
        if teil is None:
            return None
        ergebnis |= teil
    return ergebnis
