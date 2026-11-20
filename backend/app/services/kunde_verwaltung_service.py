""""Verwaltet von" am Kunden (WEG -> Hausverwaltung): Validierung und Lesen. Bewusst nur eine Ebene tief
(Konzept Abschnitt 8: keine Konzern-/Filialhierarchien)."""
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kunde import Kunde
from app.schemas.kunde_kurz import KundeKurz


def _unverarbeitbar(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


async def verwalter_pruefen(session: AsyncSession, kunde_id: UUID | None, verwalter_id: UUID | None) -> None:
    """kunde_id None beim Anlegen. Verwalter muss existieren (RLS: eigener Mandant), darf nicht der Kunde selbst
    und nicht selbst verwaltet sein; ein Kunde, der selbst Kunden verwaltet, kann nicht verwaltet werden. Damit
    sind Zyklen (A verwaltet B, B verwaltet A) und tiefere Ketten ausgeschlossen."""
    if verwalter_id is None:
        return
    if verwalter_id == kunde_id:
        raise _unverarbeitbar("Ein Kunde kann nicht von sich selbst verwaltet werden")
    verwalter = await session.get(Kunde, verwalter_id)
    if verwalter is None or verwalter.geloescht_am is not None:
        raise _unverarbeitbar("Verwaltender Kunde nicht gefunden")
    if verwalter.verwaltet_von_kunde_id is not None:
        raise _unverarbeitbar("Der verwaltende Kunde wird selbst verwaltet (nur eine Ebene möglich)")
    if kunde_id is not None:
        verwaltet = (
            await session.execute(
                select(func.count(Kunde.id)).where(
                    Kunde.verwaltet_von_kunde_id == kunde_id, Kunde.geloescht_am.is_(None)
                )
            )
        ).scalar_one()
        if verwaltet:
            raise _unverarbeitbar("Dieser Kunde verwaltet selbst Kunden (nur eine Ebene möglich)")


async def verwalter_namen(session: AsyncSession, kunden: list[Kunde]) -> dict[UUID, KundeKurz]:
    ids = {k.verwaltet_von_kunde_id for k in kunden if k.verwaltet_von_kunde_id}
    if not ids:
        return {}
    zeilen = await session.execute(select(Kunde.id, Kunde.name).where(Kunde.id.in_(ids)))
    return {z[0]: KundeKurz(id=z[0], name=z[1]) for z in zeilen}
