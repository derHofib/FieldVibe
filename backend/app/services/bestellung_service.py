from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anlage import Anlage
from app.models.bestellung import Bestellung, BestellungPosition
from app.models.material import MaterialBestand, MaterialBewegung
from app.models.material_bedarf import MaterialBedarf
from app.schemas.bestellung import BestellungPositionRead, BestellungRead

GUELTIGE_UEBERGAENGE = {"entwurf": {"bestellt", "eingegangen"}, "bestellt": {"eingegangen"}}


async def positionen_fuer(session: AsyncSession, bestellung_id: UUID) -> list[BestellungPosition]:
    result = await session.execute(
        select(BestellungPosition)
        .where(BestellungPosition.bestellung_id == bestellung_id)
        .order_by(BestellungPosition.position)
    )
    return list(result.scalars().all())


async def to_read_model(session: AsyncSession, bestellung: Bestellung) -> BestellungRead:
    positionen = await positionen_fuer(session, bestellung.id)
    return BestellungRead(
        **{k: getattr(bestellung, k) for k in BestellungRead.model_fields if k != "positionen"},
        positionen=[BestellungPositionRead.model_validate(p) for p in positionen],
    )


async def _default_lager(session: AsyncSession, mandant_id: UUID) -> Anlage:
    result = await session.execute(
        select(Anlage)
        .where(Anlage.mandant_id == mandant_id, Anlage.objekttyp == "lager")
        .order_by(Anlage.created_at.asc())
    )
    lager = result.scalars().first()
    if lager is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kein Lagerort für diesen Mandanten vorhanden",
        )
    return lager


async def _wareneingang_buchen(
    session: AsyncSession, bestellung: Bestellung, positionen: list[BestellungPosition], erstellt_von: UUID
) -> None:
    """Bucht jede Position der Bestellung als Wareneingang ins
    Zentrallager -- dieselbe Buchungslogik (MaterialBewegung +
    MaterialBestand) wie ein manueller Wareneingang, nur automatisch
    ausgeloest durch den Statuswechsel auf "eingegangen"."""
    lager = await _default_lager(session, bestellung.mandant_id)
    for position in positionen:
        result = await session.execute(
            select(MaterialBestand).where(
                MaterialBestand.material_id == position.material_id, MaterialBestand.lager_id == lager.id
            )
        )
        bestand = result.scalar_one_or_none()
        if bestand is None:
            bestand = MaterialBestand(
                mandant_id=bestellung.mandant_id,
                material_id=position.material_id,
                lager_id=lager.id,
                menge=Decimal("0"),
            )
            session.add(bestand)
        bestand.menge += position.menge
        session.add(
            MaterialBewegung(
                mandant_id=bestellung.mandant_id,
                material_id=position.material_id,
                typ="eingang",
                nach_lager_id=lager.id,
                menge=position.menge,
                erstellt_von=erstellt_von,
            )
        )

    bedarfe = (
        await session.execute(
            select(MaterialBedarf).where(MaterialBedarf.bestellung_id == bestellung.id)
        )
    ).scalars().all()
    for bedarf in bedarfe:
        bedarf.status = "erhalten"


async def apply_status_transition(
    session: AsyncSession,
    bestellung: Bestellung,
    neuer_status: str,
    *,
    erstellt_von: UUID,
    positionen_preise: dict[UUID, Decimal] | None = None,
) -> None:
    if neuer_status not in GUELTIGE_UEBERGAENGE.get(bestellung.status, set()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Statuswechsel von '{bestellung.status}' nach '{neuer_status}' nicht erlaubt",
        )

    if neuer_status == "eingegangen":
        positionen = await positionen_fuer(session, bestellung.id)
        if positionen_preise:
            bekannte_ids = {p.id for p in positionen}
            unbekannt = set(positionen_preise) - bekannte_ids
            if unbekannt:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unbekannte Position(en) in positionen_preise: {unbekannt}",
                )
            # Der bisherige Preis war nur die Planung zum Bestellzeitpunkt --
            # beim Wareneingang wird er auf den tatsaechlich bezahlten Preis
            # korrigiert, damit PDF/CSV-Export danach den echten Preis zeigen.
            for position in positionen:
                if position.id in positionen_preise:
                    position.einzelpreis = positionen_preise[position.id]
        await _wareneingang_buchen(session, bestellung, positionen, erstellt_von)

    bestellung.status = neuer_status
