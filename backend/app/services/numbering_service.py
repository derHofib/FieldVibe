from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.angebot import Angebot
from app.models.bestellung import Bestellung
from app.models.kunde import Kunde
from app.models.rechnung import Rechnung
from app.models.vorgang import Vorgang

# Kunden/Vorgaenge/Angebote/Rechnungen sind nie hart geloescht (GoBD-artige
# Aufbewahrungspflicht, siehe Abschnitt 11), also ist ein einfacher
# Zeilen-Count pro Mandant eine sichere, kollisionsfreie Basis fuer
# fortlaufende Nummern -- keine Luecken, um die man sich sorgen muesste.


async def next_kundennummer(session: AsyncSession, mandant_id: UUID) -> str:
    count = await session.scalar(
        select(func.count()).select_from(Kunde).where(Kunde.mandant_id == mandant_id)
    )
    return f"K-{count + 1:05d}"


async def next_vorgangsnummer(session: AsyncSession, mandant_id: UUID) -> str:
    count = await session.scalar(
        select(func.count()).select_from(Vorgang).where(Vorgang.mandant_id == mandant_id)
    )
    return f"V-{count + 1:05d}"


async def next_angebotsnummer(session: AsyncSession, mandant_id: UUID) -> str:
    count = await session.scalar(
        select(func.count()).select_from(Angebot).where(Angebot.mandant_id == mandant_id)
    )
    return f"A-{count + 1:05d}"


async def next_rechnungsnummer(session: AsyncSession, mandant_id: UUID) -> str:
    count = await session.scalar(
        select(func.count()).select_from(Rechnung).where(Rechnung.mandant_id == mandant_id)
    )
    return f"R-{count + 1:05d}"


async def next_bestellnummer(session: AsyncSession, mandant_id: UUID) -> str:
    count = await session.scalar(
        select(func.count()).select_from(Bestellung).where(Bestellung.mandant_id == mandant_id)
    )
    return f"B-{count + 1:05d}"
