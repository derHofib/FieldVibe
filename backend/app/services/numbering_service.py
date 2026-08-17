from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.angebot import Angebot
from app.models.beleg_zaehler import BelegZaehler
from app.models.bestellung import Bestellung
from app.models.kunde import Kunde
from app.models.vorgang import Vorgang

# Kunden/Vorgaenge/Angebote sind nie hart geloescht (GoBD-artige
# Aufbewahrungspflicht, siehe Abschnitt 11), also ist ein einfacher
# Zeilen-Count pro Mandant eine ausreichende Basis fuer ihre fortlaufenden
# Nummern -- Rechnungsnummern dagegen laufen ueber BelegZaehler (siehe
# next_rechnungsnummer unten), weil dort echte Nebenlaeufigkeit vorkommen
# kann (parallele Rechnungserstellung) und ein reiner COUNT(*)-Lesevorgang
# race-anfaellig waere.


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
    # Atomarer Upsert statt COUNT(*): zwei parallele Anfragen koennen hier
    # nicht mehr denselben Zaehlerstand lesen (siehe BelegZaehler-Docstring).
    stmt = (
        pg_insert(BelegZaehler)
        .values(mandant_id=mandant_id, belegart="rechnung", naechste_nummer=2)
        .on_conflict_do_update(
            index_elements=[BelegZaehler.mandant_id, BelegZaehler.belegart],
            set_={"naechste_nummer": BelegZaehler.naechste_nummer + 1},
        )
        .returning(BelegZaehler.naechste_nummer)
    )
    ergebnis = await session.execute(stmt)
    vergebene_nummer = ergebnis.scalar_one() - 1
    return f"R-{vergebene_nummer:05d}"


async def next_bestellnummer(session: AsyncSession, mandant_id: UUID) -> str:
    count = await session.scalar(
        select(func.count()).select_from(Bestellung).where(Bestellung.mandant_id == mandant_id)
    )
    return f"B-{count + 1:05d}"
