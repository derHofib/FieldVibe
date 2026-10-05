"""Baum- und Ableitungs-Helfer fuer die Organigramm-API (routes/organigramm.py)."""
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rechte_registry import SCOPE_RANG
from app.models.account_typ import AccountTypRecht
from app.models.organigramm import Position, PositionBesetzung, PositionRecht

_ERLAUBTE_TABELLEN = ("positionen", "org_einheiten")


def jetzt() -> datetime:
    return datetime.now(timezone.utc)


async def baum_sperren(session: AsyncSession, mandant_id: UUID) -> None:
    """Serialisiert Struktur-Aenderungen je Mandant (Umhaengen/Archivieren/Loeschen),
    damit zwei gleichzeitige Umhaengungen keinen Zyklus erzeugen. Transaktionsgebunden."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"organigramm:{mandant_id}"}
    )


async def pfad_zur_wurzel(
    session: AsyncSession, tabelle: str, mandant_id: UUID, start_id: UUID
) -> set[UUID]:
    """start_id und alle Vorfahren (rekursive CTE). Liegt ein Knoten im Pfad des
    neuen Elternknotens, wuerde das Umhaengen einen Zyklus erzeugen."""
    if tabelle not in _ERLAUBTE_TABELLEN:
        raise ValueError(tabelle)
    zeilen = await session.execute(
        text(
            f"""
            WITH RECURSIVE pfad(id, parent_id) AS (
              SELECT id, parent_id FROM {tabelle} WHERE id = :start AND mandant_id = :m
              UNION
              SELECT t.id, t.parent_id FROM {tabelle} t JOIN pfad ON t.id = pfad.parent_id
              WHERE t.mandant_id = :m
            )
            SELECT id FROM pfad
            """
        ),
        {"start": start_id, "m": mandant_id},
    )
    return {row[0] for row in zeilen}


def ist_aktiv(besetzung: PositionBesetzung, stichtag: datetime) -> bool:
    return besetzung.gueltig_von <= stichtag and (
        besetzung.gueltig_bis is None or besetzung.gueltig_bis > stichtag
    )


async def aktive_besetzungen(
    session: AsyncSession, mandant_id: UUID, stichtag: datetime, position_id: UUID | None = None
) -> dict[UUID, list[PositionBesetzung]]:
    stmt = select(PositionBesetzung).where(
        PositionBesetzung.mandant_id == mandant_id,
        PositionBesetzung.gueltig_von <= stichtag,
        or_(PositionBesetzung.gueltig_bis.is_(None), PositionBesetzung.gueltig_bis > stichtag),
    )
    if position_id is not None:
        stmt = stmt.where(PositionBesetzung.position_id == position_id)
    je_position: dict[UUID, list[PositionBesetzung]] = defaultdict(list)
    for b in (await session.execute(stmt.order_by(PositionBesetzung.gueltig_von))).scalars():
        je_position[b.position_id].append(b)
    return je_position


def status_von(position: Position, anzahl_aktiv: int) -> str:
    if anzahl_aktiv > 0:
        return "besetzt"
    return "geplant" if position.geplant else "vakant"


def position_snapshot(p: Position) -> dict[str, Any]:
    return {
        "id": p.id,
        "parent_id": p.parent_id,
        "typ": p.typ,
        "titel": p.titel,
        "ebene": p.ebene,
        "org_einheit_id": p.org_einheit_id,
        "account_typ_id": p.account_typ_id,
        "geplant": p.geplant,
        "soll_besetzung": p.soll_besetzung,
        "gueltig_ab": p.gueltig_ab,
        "gueltig_bis": p.gueltig_bis,
        "archiviert_am": p.archiviert_am,
        "reihenfolge": p.reihenfolge,
    }


def besetzung_snapshot(b: PositionBesetzung) -> dict[str, Any]:
    return {
        "id": b.id,
        "position_id": b.position_id,
        "user_id": b.user_id,
        "art": b.art,
        "gueltig_von": b.gueltig_von,
        "gueltig_bis": b.gueltig_bis,
    }


def overrides_snapshot(zeilen) -> list[dict[str, Any]]:
    return sorted(
        ({"bereich": o.bereich, "aktion": o.aktion, "wirkung": o.wirkung, "scope": o.scope} for o in zeilen),
        key=lambda e: (e["bereich"], e["aktion"]),
    )


async def position_effektiv(
    session: AsyncSession, position: Position
) -> tuple[list[dict], list[dict], list[dict]]:
    """(effektive Rechte mit Herkunft, Diff zur Typ-Vorlage, Overrides) einer
    Position nach denselben Regeln wie die Engine (Typ-Basis + Overrides)."""
    basis: dict[tuple[str, str], str] = {}
    if position.account_typ_id is not None:
        for r in (
            await session.execute(
                select(AccountTypRecht).where(
                    AccountTypRecht.account_typ_id == position.account_typ_id,
                    AccountTypRecht.erlaubt.is_(True),
                )
            )
        ).scalars():
            basis[(r.bereich, r.aktion)] = r.scope
    overrides = (
        (await session.execute(select(PositionRecht).where(PositionRecht.position_id == position.id)))
        .scalars()
        .all()
    )
    eff: dict[tuple[str, str], tuple[str, list[dict]]] = {
        key: (
            scope,
            [{"art": "account_typ", "account_typ_id": str(position.account_typ_id)}],
        )
        for key, scope in basis.items()
    }
    for o in sorted(overrides, key=lambda x: (x.bereich, x.aktion)):
        key = (o.bereich, o.aktion)
        herkunft = {"art": "position_override", "wirkung": o.wirkung}
        if o.wirkung == "verweigern":
            eff.pop(key, None)
            continue
        alt = eff.get(key)
        scope = o.scope or (alt[0] if alt else "mandant")
        if alt is not None and SCOPE_RANG[alt[0]] > SCOPE_RANG[scope]:
            scope = alt[0]
        eff[key] = (scope, (alt[1] if alt else []) + [herkunft])

    rechte = [
        {"bereich": b, "aktion": a, "scope": scope, "herkunft": herkunft}
        for (b, a), (scope, herkunft) in sorted(eff.items())
    ]
    diff: list[dict] = []
    for key in sorted(set(basis) | set(eff)):
        in_basis, in_eff = key in basis, key in eff
        if in_eff and not in_basis:
            art = "hinzugefuegt"
        elif in_basis and not in_eff:
            art = "entfernt"
        elif basis[key] != eff[key][0]:
            art = "scope_geaendert"
        else:
            continue
        diff.append(
            {
                "bereich": key[0],
                "aktion": key[1],
                "art": art,
                "typ_scope": basis.get(key),
                "position_scope": eff[key][0] if in_eff else None,
            }
        )
    return rechte, diff, overrides_snapshot(overrides)
