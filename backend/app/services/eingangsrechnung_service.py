from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.eingangsrechnung import Eingangsrechnung, EingangsrechnungPosition
from app.schemas.eingangsrechnung import EingangsrechnungPositionRead, EingangsrechnungRead

_CENT = Decimal("0.01")


async def positionen_fuer(session: AsyncSession, eingangsrechnung_id: UUID) -> list[EingangsrechnungPosition]:
    result = await session.execute(
        select(EingangsrechnungPosition)
        .where(EingangsrechnungPosition.eingangsrechnung_id == eingangsrechnung_id)
        .order_by(EingangsrechnungPosition.position)
    )
    return list(result.scalars().all())


def netto_betrag(
    eingangsrechnung: Eingangsrechnung, positionen: list[EingangsrechnungPosition]
) -> Decimal:
    """Gleiche Logik wie bei Rechnung: Positionen (falls vorhanden) sind die
    Quelle der Wahrheit, sonst bleibt der manuell erfasste betrag_netto
    massgeblich -- viele Eingangsbelege sind einfache Pauschalrechnungen
    ohne eigene Zeilen."""
    if positionen:
        return sum((p.menge * p.einzelpreis for p in positionen), Decimal("0")).quantize(_CENT)
    return eingangsrechnung.betrag_netto.quantize(_CENT)


async def to_read_model(session: AsyncSession, eingangsrechnung: Eingangsrechnung) -> EingangsrechnungRead:
    positionen = await positionen_fuer(session, eingangsrechnung.id)
    netto = netto_betrag(eingangsrechnung, positionen)
    return EingangsrechnungRead(
        **{
            k: getattr(eingangsrechnung, k)
            for k in EingangsrechnungRead.model_fields
            if k not in ("positionen", "betrag_netto", "betrag_brutto")
        },
        betrag_netto=netto,
        positionen=[EingangsrechnungPositionRead.model_validate(p) for p in positionen],
    )
