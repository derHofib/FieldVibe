"""Read-only Konsistenzpruefung Organigramm <-> bisherige Rechtevergabe.

Dient der Migrationskontrolle (docs/konzepte/ORGANIGRAMM.md): solange die
Rechte-Engine noch users.account_typ_id nutzt, muss die aus den Positionen
abgeleitete Matrix fuer jeden aktiven Nutzer identisch sein.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account_typ import AccountTypRecht
from app.models.mandant import Mandant
from app.models.organigramm import Position, PositionBesetzung
from app.models.user import User


@dataclass
class MandantPruefung:
    mandant_id: UUID
    name: str
    positionen: int = 0
    besetzungen: int = 0
    nutzer_geprueft: int = 0
    zeilen: list[str] = field(default_factory=list)
    abweichungen: list[str] = field(default_factory=list)


@dataclass
class PruefErgebnis:
    mandanten: list[MandantPruefung] = field(default_factory=list)

    @property
    def abweichungen(self) -> list[str]:
        return [a for m in self.mandanten for a in m.abweichungen]


def _matrix_text(matrix: set[tuple[str, str]]) -> str:
    return ", ".join(f"{b}.{a}" for b, a in sorted(matrix)) or "(leer)"


async def organigramm_pruefen(session: AsyncSession, *, mandant_id: UUID | None = None) -> PruefErgebnis:
    """Erwartet eine Session ohne Mandanten-Einschraenkung (system_session)."""
    query = select(Mandant).order_by(Mandant.name)
    if mandant_id is not None:
        query = query.where(Mandant.id == mandant_id)
    ergebnis = PruefErgebnis()

    for mandant in (await session.execute(query)).scalars().all():
        pruefung = MandantPruefung(mandant_id=mandant.id, name=mandant.name)
        ergebnis.mandanten.append(pruefung)

        positionen = (
            (await session.execute(select(Position).where(Position.mandant_id == mandant.id)))
            .scalars()
            .all()
        )
        nutzer = {
            u.id: u
            for u in (
                await session.execute(
                    select(User).where(User.mandant_id == mandant.id, User.aktiv.is_(True))
                )
            )
            .scalars()
            .all()
        }
        besetzungen = (
            (
                await session.execute(
                    select(PositionBesetzung).where(
                        PositionBesetzung.mandant_id == mandant.id, PositionBesetzung.gueltig_bis.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        rechte_je_typ: dict[UUID, set[tuple[str, str]]] = defaultdict(set)
        for recht in (
            (await session.execute(select(AccountTypRecht).where(AccountTypRecht.mandant_id == mandant.id)))
            .scalars()
            .all()
        ):
            if recht.erlaubt:
                rechte_je_typ[recht.account_typ_id].add((recht.bereich, recht.aktion))

        pos_nach_id = {p.id: p for p in positionen}
        besetzt_von: dict[UUID, list[PositionBesetzung]] = defaultdict(list)
        pos_je_nutzer: dict[UUID, list[Position]] = defaultdict(list)
        for b in besetzungen:
            position = pos_nach_id.get(b.position_id)
            if position is None:
                continue
            besetzt_von[position.id].append(b)
            pos_je_nutzer[b.user_id].append(position)

        pruefung.positionen = len(positionen)
        pruefung.besetzungen = len(besetzungen)

        kinder: dict[UUID | None, list[Position]] = defaultdict(list)
        for p in positionen:
            kinder[p.parent_id].append(p)

        def _zeilen(parent_id: UUID | None, tiefe: int) -> None:
            for p in sorted(kinder.get(parent_id, []), key=lambda x: (x.reihenfolge, x.titel)):
                namen = ", ".join(
                    sorted(nutzer[b.user_id].name for b in besetzt_von.get(p.id, []) if b.user_id in nutzer)
                )
                pruefung.zeilen.append(
                    f"{'  ' * tiefe}- {p.titel} [{len(besetzt_von.get(p.id, []))}/{p.soll_besetzung}]"
                    + (f": {namen}" if namen else "")
                )
                _zeilen(p.id, tiefe + 1)

        _zeilen(None, 0)

        for user in sorted(nutzer.values(), key=lambda u: u.email):
            if user.role not in ("custom", "mandant_admin"):
                continue
            pruefung.nutzer_geprueft += 1
            ihre_positionen = pos_je_nutzer.get(user.id, [])
            kennung = f"{mandant.name}: {user.email} ({user.role})"

            if user.role == "mandant_admin":
                if not any(p.parent_id is None for p in ihre_positionen):
                    pruefung.abweichungen.append(f"{kennung}: sitzt nicht auf der Wurzelposition")
                continue

            if user.account_typ_id is None:
                continue
            passende = [p for p in ihre_positionen if p.account_typ_id == user.account_typ_id]
            if len(passende) != 1:
                pruefung.abweichungen.append(
                    f"{kennung}: {len(passende)} aktive Besetzungen auf Positionen mit Account-Typ "
                    f"{user.account_typ_id} (erwartet: genau 1)"
                )
            alt = rechte_je_typ.get(user.account_typ_id, set())
            neu: set[tuple[str, str]] = set()
            for p in ihre_positionen:
                if p.account_typ_id is not None:
                    neu |= rechte_je_typ.get(p.account_typ_id, set())
            if alt != neu:
                pruefung.abweichungen.append(
                    f"{kennung}: Rechte-Matrix weicht ab (nur alt: {_matrix_text(alt - neu)}; "
                    f"nur neu: {_matrix_text(neu - alt)})"
                )
    return ergebnis
