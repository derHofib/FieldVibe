from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rechnung import Rechnung, RechnungPosition
from app.schemas.rechnung import RechnungPositionRead, RechnungRead

_CENT = Decimal("0.01")


async def positionen_fuer(session: AsyncSession, rechnung_id: UUID) -> list[RechnungPosition]:
    result = await session.execute(
        select(RechnungPosition)
        .where(RechnungPosition.rechnung_id == rechnung_id)
        .order_by(RechnungPosition.position)
    )
    return list(result.scalars().all())


def netto_betrag(rechnung: Rechnung, positionen: list[RechnungPosition]) -> Decimal:
    """Positionen (falls vorhanden) sind die Quelle der Wahrheit, dieselbe
    Ueberlegung wie bei Angebot.gesamt_netto: verhindert eine veraltete Summe
    nach nachtraeglicher Preisaenderung einer Position. Ohne Positionen (der
    einfache Fall aus Phase 6, eine Abschlussrechnung ohne eigene Zeilen)
    bleibt der manuell gesetzte betrag_netto massgeblich."""
    if positionen:
        return sum((p.menge * p.einzelpreis for p in positionen), Decimal("0")).quantize(_CENT)
    return rechnung.betrag_netto.quantize(_CENT)


async def to_read_model(session: AsyncSession, rechnung: Rechnung) -> RechnungRead:
    positionen = await positionen_fuer(session, rechnung.id)
    netto = netto_betrag(rechnung, positionen)
    return RechnungRead(
        **{
            k: getattr(rechnung, k)
            for k in RechnungRead.model_fields
            if k not in ("positionen", "betrag_netto", "betrag_brutto")
        },
        betrag_netto=netto,
        positionen=[RechnungPositionRead.model_validate(p) for p in positionen],
    )
