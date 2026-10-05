"""Eskalationsschutz und Admin-Sicherung fuer alle Rechte-Schreibpfade
(docs/konzepte/ORGANIGRAMM.md, "Eskalationsschutz"): Organigramm-API,
Account-Typen, Users-PATCH.

Regeln:
  - Wer Rechte vergibt, braucht rechte_verwalten (organigramm ODER
    mitarbeiterverwaltung) und darf nur (bereich, aktion, scope) gewaehren, die er
    selbst mit mindestens gleichem Scope hat. "verweigern" macht nichts maechtiger
    und braucht keine Eigenrechte, nur den Scope auf das Ziel.
  - Ziel (Position/Nutzer/Account-Typ) muss im Scope des Akteurs liegen.
  - role != custom (mandant_admin, loesch_operativ ...) hat alle Rechte und unterliegt
    keiner Einschraenkung.
  - Letzter aktiver mandant_admin nicht entfernbar; es bleibt immer mind. ein
    aktiver Nutzer mit mandantweitem rechte_verwalten (mandant_admin zaehlt immer).
"""
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Iterable
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rechte_registry import SCOPE_RANG
from app.models.account_typ import AccountTypRecht
from app.models.organigramm import Position, PositionBesetzung
from app.models.user import User
from app.services import berechtigung_service as bs
from app.services.user_anonymisierung_service import nicht_anonymisiert

RechtKey = tuple[str, str]
RechtMap = dict[RechtKey, str]
# (bereich, aktion, wirkung, scope)
OverrideTupel = tuple[str, str, str, str | None]

RECHTE_VERWALTEN: tuple[RechtKey, ...] = (
    ("organigramm", "rechte_verwalten"),
    ("mitarbeiterverwaltung", "rechte_verwalten"),
)


def verboten(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


@dataclass
class Akteur:
    auth: Any
    rechte: bs.EffektiveRechte

    @property
    def ist_admin(self) -> bool:
        return self.rechte.alle_rechte

    def hat(self, bereich: str, aktion: str) -> bool:
        return self.rechte.hat(bereich, aktion)

    def hat_eines(self, keys: Iterable[RechtKey]) -> bool:
        return any(self.hat(b, a) for b, a in keys)


async def akteur_laden(session: AsyncSession, auth: Any) -> Akteur:
    rechte = await bs.effektive_rechte_gecacht(session, user_id=auth.user_id, rolle=auth.role)
    return Akteur(auth=auth, rechte=rechte)


def recht_pflicht(akteur: Akteur, bereich: str, aktion: str) -> None:
    if not akteur.hat(bereich, aktion):
        raise verboten("Keine Berechtigung für diese Aktion")


def rechte_verwalten_pflicht(akteur: Akteur) -> None:
    if not akteur.hat_eines(RECHTE_VERWALTEN):
        raise verboten("Zum Vergeben von Rechten ist das Recht „Rechte verwalten“ erforderlich")


# --- Scope-Mengen --------------------------------------------------------------


async def position_ids_im_scope(
    session: AsyncSession, akteur: Akteur, keys: Iterable[RechtKey]
) -> set[UUID] | None:
    """Positionen, auf die sich die Rechte `keys` des Akteurs erstrecken (Vereinigung);
    None = alle (mandant bzw. Admin). "eigene" = nur die selbst besetzten Positionen."""
    if akteur.ist_admin:
        return None
    ergebnis: set[UUID] = set()
    for key in keys:
        je_position = akteur.rechte.gewaehrende_positionen.get(key)
        if not je_position:
            continue
        nach_scope: dict[str, list[UUID]] = defaultdict(list)
        for pid, scope in je_position.items():
            nach_scope[scope].append(pid)
        for scope, pids in nach_scope.items():
            if scope == "mandant":
                return None
            teil = set(pids)
            if scope != "eigene":
                teil |= await bs._team_position_ids(session, pids)
                if SCOPE_RANG[scope] >= SCOPE_RANG["teilbaum"]:
                    teil |= await bs._teilbaum_position_ids(session, pids)
                if SCOPE_RANG[scope] >= SCOPE_RANG["bereich"]:
                    teil |= await bs._bereich_position_ids(session, pids)
            ergebnis |= teil
    return ergebnis


async def user_ids_im_scope(
    session: AsyncSession, akteur: Akteur, keys: Iterable[RechtKey]
) -> set[UUID] | None:
    if akteur.ist_admin:
        return None
    ergebnis: set[UUID] = set()
    for bereich, aktion in keys:
        if not akteur.hat(bereich, aktion):
            continue
        teil = await bs.user_ids_fuer_recht(session, akteur.auth, bereich, aktion)
        if teil is None:
            return None
        ergebnis |= teil
    return ergebnis


async def position_im_scope_pruefen(
    session: AsyncSession, akteur: Akteur, keys: Iterable[RechtKey], position_ids: Iterable[UUID]
) -> None:
    erlaubt = await position_ids_im_scope(session, akteur, tuple(keys))
    if erlaubt is None:
        return
    if any(pid not in erlaubt for pid in position_ids):
        raise verboten("Die Position liegt außerhalb Ihres Verantwortungsbereichs")


async def user_im_scope_pruefen(
    session: AsyncSession, akteur: Akteur, keys: Iterable[RechtKey], user_id: UUID
) -> None:
    erlaubt = await user_ids_im_scope(session, akteur, tuple(keys))
    if erlaubt is not None and user_id not in erlaubt:
        raise verboten("Der Nutzer liegt außerhalb Ihres Verantwortungsbereichs")


async def typ_im_scope_pruefen(session: AsyncSession, akteur: Akteur, account_typ_id: UUID) -> None:
    """Ein Account-Typ wirkt auf alle seine Positionen: besetzte Positionen
    ausserhalb des Scopes sperren Aenderungen am Typ fuer Nicht-Admins."""
    if akteur.ist_admin:
        return
    belegt = {
        row[0]
        for row in await session.execute(
            select(Position.id)
            .join(PositionBesetzung, PositionBesetzung.position_id == Position.id)
            .where(Position.account_typ_id == account_typ_id, PositionBesetzung.gueltig_bis.is_(None))
        )
    }
    if belegt:
        erlaubt = await position_ids_im_scope(session, akteur, RECHTE_VERWALTEN)
        if erlaubt is not None and not belegt <= erlaubt:
            raise verboten("Der Account-Typ wird auch außerhalb Ihres Verantwortungsbereichs verwendet")


# --- Rechte-Vergabe -----------------------------------------------------------


def _groesser(a: str | None, b: str) -> str:
    return b if a is None or SCOPE_RANG[b] > SCOPE_RANG[a] else a


async def typ_rechte_map(session: AsyncSession, account_typ_id: UUID | None) -> RechtMap:
    if account_typ_id is None:
        return {}
    zeilen = await session.execute(
        select(AccountTypRecht).where(
            AccountTypRecht.account_typ_id == account_typ_id, AccountTypRecht.erlaubt.is_(True)
        )
    )
    return {(r.bereich, r.aktion): r.scope for r in zeilen.scalars()}


async def position_rechte_map(
    session: AsyncSession, account_typ_id: UUID | None, overrides: Iterable[OverrideTupel]
) -> RechtMap:
    """Rechte einer Position nach Engine-Regeln (Typ-Basis + Overrides), ohne Nutzer."""
    ergebnis = await typ_rechte_map(session, account_typ_id)
    for bereich, aktion, wirkung, scope in overrides:
        key = (bereich, aktion)
        if wirkung == "verweigern":
            ergebnis.pop(key, None)
            continue
        neu = scope or ergebnis.get(key) or "mandant"
        ergebnis[key] = _groesser(ergebnis.get(key), neu)
    return ergebnis


def user_override_map(overrides: Iterable[OverrideTupel]) -> RechtMap:
    """Nur erlauben-Eintraege; scope=None zaehlt streng als mandant (ohne Basis unbekannt)."""
    return {(b, a): (s or "mandant") for b, a, w, s in overrides if w == "erlauben"}


def mehr_rechte_pruefen(akteur: Akteur, neu: RechtMap, alt: RechtMap | None = None) -> None:
    """Jedes neu hinzukommende oder im Scope erweiterte Recht muss der Akteur selbst
    mit mindestens gleichem Scope haben (rechte_verwalten wird separat geprueft)."""
    if akteur.ist_admin:
        return
    for (bereich, aktion), scope in neu.items():
        if alt is not None and (bereich, aktion) in alt and SCOPE_RANG[alt[(bereich, aktion)]] >= SCOPE_RANG[scope]:
            continue
        eigen = akteur.rechte.scope(bereich, aktion)
        if eigen is None or SCOPE_RANG[eigen] < SCOPE_RANG[scope]:
            raise verboten(
                f"Das Recht „{bereich}.{aktion}“ mit Reichweite „{scope}“ darf nicht vergeben werden: "
                "Sie haben es selbst nicht in diesem Umfang"
            )


def flags_pruefen(akteur: Akteur, flags: Iterable[str]) -> None:
    """Typ-Flags (darf_zeiten_buchen ...) darf nur einschalten, wer sie selbst hat."""
    if akteur.ist_admin:
        return
    for flag in flags:
        if not akteur.rechte.flag(flag):
            raise verboten(f"Die Berechtigung „{flag}“ darf nicht vergeben werden: Sie haben sie selbst nicht")


async def user_effektiv_map(session: AsyncSession, user: User, *, stichtag=None) -> RechtMap:
    """Aufgeloeste Rechte eines Nutzers (ohne Cache); role != custom hat ohnehin alles."""
    if user.role != "custom":
        return {}
    rechte = await bs.effektive_rechte(session, user_id=user.id, rolle=user.role, stichtag=stichtag)
    return {key: recht.scope for key, recht in rechte.rechte.items()}


# --- Letzter Admin ---------------------------------------------------------------


async def andere_aktive_admins(session: AsyncSession, mandant_id: UUID, ausser_user_id: UUID) -> int:
    return await session.scalar(
        select(func.count()).select_from(User).where(
            User.mandant_id == mandant_id,
            User.role == "mandant_admin",
            User.aktiv.is_(True),
            User.id != ausser_user_id,
            nicht_anonymisiert(),
        )
    )


async def letzten_admin_pruefen(session: AsyncSession, user: User) -> None:
    """409, wenn `user` der letzte aktive mandant_admin seines Mandanten ist.
    Vor dem Deaktivieren/Loeschen/Anonymisieren/Herabstufen aufrufen."""
    if user.role != "mandant_admin" or not user.aktiv or user.mandant_id is None:
        return
    if await andere_aktive_admins(session, user.mandant_id, user.id) == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Der letzte aktive Mandanten-Admin kann nicht deaktiviert, gelöscht oder herabgestuft werden",
        )


async def verwaltung_vorhanden(session: AsyncSession, mandant_id: UUID) -> bool:
    """Gibt es einen aktiven mandant_admin oder einen aktiven Nutzer, der
    rechte_verwalten (organigramm/mitarbeiterverwaltung) mit Scope mandant hat?"""
    admin = await session.scalar(
        select(User.id)
        .where(
            User.mandant_id == mandant_id,
            User.role == "mandant_admin",
            User.aktiv.is_(True),
            nicht_anonymisiert(),
        )
        .limit(1)
    )
    if admin is not None:
        return True
    kandidaten = (
        await session.execute(
            select(User).where(
                User.mandant_id == mandant_id,
                User.role == "custom",
                User.aktiv.is_(True),
                nicht_anonymisiert(),
            )
        )
    ).scalars()
    for nutzer in kandidaten:
        rechte = await bs.effektive_rechte(session, user_id=nutzer.id, rolle=nutzer.role)
        if any(rechte.scope(b, a) == "mandant" for b, a in RECHTE_VERWALTEN):
            return True
    return False


@asynccontextmanager
async def verwaltung_bleibt_erhalten(session: AsyncSession, mandant_id: UUID | None):
    """Um jede Aenderung, die Rechte/Besetzungen/Nutzerstatus beruehrt: war vorher
    jemand mit mandantweitem rechte_verwalten da, muss auch nachher einer da sein.
    (Relativ geprueft, damit ein Mandant ohne Verwalter -- Altbestand/Tests -- nicht
    jede Aenderung blockiert.)"""
    if mandant_id is None:
        yield
        return
    vorher = await verwaltung_vorhanden(session, mandant_id)
    yield
    if not vorher:
        return
    await session.flush()
    bs.cache_leeren(session)
    if not await verwaltung_vorhanden(session, mandant_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Die Änderung ist nicht möglich: Danach könnte niemand mehr mandantweit Rechte verwalten",
        )
