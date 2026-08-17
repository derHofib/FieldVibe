from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.eingangsrechnung import (
    Eingangsrechnung,
    EingangsrechnungPosition,
    EingangsrechnungZahlung,
)
from app.schemas.eingangsrechnung import (
    EingangsrechnungPositionRead,
    EingangsrechnungRead,
    EingangsrechnungZahlungRead,
)

_CENT = Decimal("0.01")


async def positionen_fuer(session: AsyncSession, eingangsrechnung_id: UUID) -> list[EingangsrechnungPosition]:
    result = await session.execute(
        select(EingangsrechnungPosition)
        .where(EingangsrechnungPosition.eingangsrechnung_id == eingangsrechnung_id)
        .order_by(EingangsrechnungPosition.position)
    )
    return list(result.scalars().all())


async def zahlungen_fuer(session: AsyncSession, eingangsrechnung_id: UUID) -> list[EingangsrechnungZahlung]:
    result = await session.execute(
        select(EingangsrechnungZahlung)
        .where(EingangsrechnungZahlung.eingangsrechnung_id == eingangsrechnung_id)
        .order_by(EingangsrechnungZahlung.datum, EingangsrechnungZahlung.created_at)
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


def bezahlter_betrag(zahlungen: list[EingangsrechnungZahlung]) -> Decimal:
    return sum((z.betrag for z in zahlungen), Decimal("0")).quantize(_CENT)


def brutto_betrag(eingangsrechnung: Eingangsrechnung, positionen: list[EingangsrechnungPosition]) -> Decimal:
    netto = netto_betrag(eingangsrechnung, positionen)
    return (netto + netto * eingangsrechnung.mwst_satz / Decimal("100")).quantize(_CENT)


async def to_read_model(session: AsyncSession, eingangsrechnung: Eingangsrechnung) -> EingangsrechnungRead:
    positionen = await positionen_fuer(session, eingangsrechnung.id)
    zahlungen = await zahlungen_fuer(session, eingangsrechnung.id)
    netto = netto_betrag(eingangsrechnung, positionen)
    return EingangsrechnungRead(
        **{
            k: getattr(eingangsrechnung, k)
            for k in EingangsrechnungRead.model_fields
            if k not in ("positionen", "zahlungen", "betrag_netto", "betrag_brutto", "bezahlter_betrag", "offener_betrag", "skonto_frist", "skonto_betrag")
        },
        betrag_netto=netto,
        positionen=[EingangsrechnungPositionRead.model_validate(p) for p in positionen],
        zahlungen=[EingangsrechnungZahlungRead.model_validate(z) for z in zahlungen],
    )
