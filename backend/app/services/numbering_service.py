from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import InstrumentedAttribute

from app.models.angebot import Angebot
from app.models.beleg_zaehler import BelegZaehler
from app.models.bestellung import Bestellung
from app.models.kunde import Kunde
from app.models.vorgang import Vorgang

# Alle fortlaufenden Nummern laufen ueber BelegZaehler (atomarer Upsert), nicht
# ueber COUNT(*): Datensaetze koennen im Papierkorb endgueltig geloescht werden
# (papierkorb_service.purge), der Count sinkt dann und die naechste Nummer waere
# schon vergeben; ausserdem waere ein Count-Lesevorgang bei paralleler Anlage
# race-anfaellig. Der Zaehler zaehlt nur hoch, geloeschte Nummern werden nie
# wiederverwendet.

# Kunden und Vorgaenge duerfen ihre Nummer manuell setzen (POST /api/kunden,
# POST /api/vorgaenge) -- eine solche Nummer kann ueber dem Zaehlerstand liegen,
# deshalb prueft _vergebe_nummer vor der Rueckgabe gegen den Bestand.
_MAX_VERSUCHE = 1000


async def _naechste_laufnummer(session: AsyncSession, mandant_id: UUID, belegart: str) -> int:
    # Atomarer Upsert statt COUNT(*): zwei parallele Anfragen koennen hier
    # nicht mehr denselben Zaehlerstand lesen (siehe BelegZaehler-Docstring).
    # naechste_nummer ist die noch nicht vergebene Nummer, daher -1 fuer die
    # soeben reservierte.
    stmt = (
        pg_insert(BelegZaehler)
        .values(mandant_id=mandant_id, belegart=belegart, naechste_nummer=2)
        .on_conflict_do_update(
            index_elements=[BelegZaehler.mandant_id, BelegZaehler.belegart],
            set_={"naechste_nummer": BelegZaehler.naechste_nummer + 1},
        )
        .returning(BelegZaehler.naechste_nummer)
    )
    ergebnis = await session.execute(stmt)
    return ergebnis.scalar_one() - 1


async def _vergebe_nummer(
    session: AsyncSession,
    mandant_id: UUID,
    *,
    belegart: str,
    praefix: str,
    modell,
    nummernspalte: InstrumentedAttribute,
) -> str:
    for _ in range(_MAX_VERSUCHE):
        laufnummer = await _naechste_laufnummer(session, mandant_id, belegart)
        nummer = f"{praefix}-{laufnummer:05d}"
        # Bewusst ohne geloescht_am-Filter: auch Papierkorb-Eintraege halten
        # die Nummer fuer den UniqueConstraint (mandant_id, nummer) belegt.
        vorhanden = await session.scalar(
            select(modell.id).where(modell.mandant_id == mandant_id, nummernspalte == nummer).limit(1)
        )
        if vorhanden is None:
            return nummer
    raise RuntimeError(
        f"Keine freie Nummer fuer Belegart '{belegart}' gefunden (Mandant {mandant_id}, "
        f"{_MAX_VERSUCHE} Versuche) -- Nummernkreis pruefen."
    )


async def next_kundennummer(session: AsyncSession, mandant_id: UUID) -> str:
    return await _vergebe_nummer(
        session, mandant_id, belegart="kunde", praefix="K", modell=Kunde, nummernspalte=Kunde.kundennummer
    )


async def next_vorgangsnummer(session: AsyncSession, mandant_id: UUID) -> str:
    return await _vergebe_nummer(
        session, mandant_id, belegart="vorgang", praefix="V", modell=Vorgang, nummernspalte=Vorgang.vorgangsnummer
    )


async def next_angebotsnummer(session: AsyncSession, mandant_id: UUID) -> str:
    return await _vergebe_nummer(
        session, mandant_id, belegart="angebot", praefix="A", modell=Angebot, nummernspalte=Angebot.angebotsnummer
    )


async def next_rechnungsnummer(session: AsyncSession, mandant_id: UUID) -> str:
    # Ohne Bestandspruefung: Rechnungsnummern werden nie manuell vergeben.
    return f"R-{await _naechste_laufnummer(session, mandant_id, 'rechnung'):05d}"


async def next_bestellnummer(session: AsyncSession, mandant_id: UUID) -> str:
    return await _vergebe_nummer(
        session,
        mandant_id,
        belegart="bestellung",
        praefix="B",
        modell=Bestellung,
        nummernspalte=Bestellung.bestellnummer,
    )
