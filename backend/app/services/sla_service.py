"""SLA am Vorgang (docs/konzepte/SLA.md, Abschnitte 3 und 5).

Einzige Stelle, die die sla_*-Felder des Vorgangs schreibt. Zeitmodell: Die Uhr
laeuft in Abschnitten (sla_laeuft_seit). Beim Anhalten (wartet_kunde) oder bei
einer Prioritaetsaenderung wird der laufende Abschnitt in sla_*_verbraucht_min
verbucht; die Faelligkeit ist dann laeuft_seit + (Ziel - verbraucht) in
Geschaeftszeit. So bleibt die Rechnung auch mit Geschaeftszeiten korrekt.

Vorgaenge aus Dauerauftraegen und Pruefzyklen (Scheduler) erhalten keine SLA:
dort steuert die Toleranz in prioritaet_service die Dringlichkeit."""
from datetime import date, datetime, time, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mandant import Mandant
from app.models.sla import SlaRichtlinie
from app.models.vertrag import Vertrag
from app.models.vorgang import Vorgang
from app.services.sla_kalender import SlaKalender, add_geschaeftsminuten, geschaeftsminuten_zwischen

FristArt = Literal["reaktion", "loesung"]
ABGESCHLOSSEN_STATUS = ("abgeschlossen", "abgerechnet", "storniert")
# Anzeige "gefaehrdet" ab diesem Anteil der (Wanduhr-)Frist; die Eskalation in
# Phase 4 rechnet exakt in Geschaeftszeit.
GEFAEHRDET_AB = 0.75


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


def kalender_von(richtlinie: SlaRichtlinie, bundesland: str | None) -> SlaKalender:
    fenster = {
        int(tag): tuple((time.fromisoformat(von), time.fromisoformat(bis)) for von, bis in paare)
        for tag, paare in (richtlinie.geschaeftszeiten or {}).items()
    }
    return SlaKalender(
        fenster=fenster,
        rund_um_die_uhr=richtlinie.kalender == "rund_um_die_uhr",
        feiertage_ausnehmen=richtlinie.feiertage_ausnehmen,
        bundesland=bundesland,
    )


def ziel_min(richtlinie: SlaRichtlinie, prioritaet: int, art: FristArt) -> int | None:
    return ((richtlinie.ziele or {}).get(str(prioritaet)) or {}).get(f"{art}_min")


async def richtlinie_aufloesen(session: AsyncSession, vorgang: Vorgang, *, am: date | None = None) -> SlaRichtlinie | None:
    """Vertrag (aktiv, innerhalb der Laufzeit) vor Mandanten-Standard."""
    heute = am or _jetzt().date()
    if vorgang.vertrag_id is not None:
        vertrag = await session.get(Vertrag, vorgang.vertrag_id)
        if (
            vertrag is not None
            and vertrag.geloescht_am is None
            and vertrag.aktiv
            and vertrag.sla_richtlinie_id is not None
            and (vertrag.laufzeit_von is None or vertrag.laufzeit_von <= heute)
            and (vertrag.laufzeit_bis is None or vertrag.laufzeit_bis >= heute)
        ):
            richtlinie = await session.get(SlaRichtlinie, vertrag.sla_richtlinie_id)
            if richtlinie is not None and richtlinie.aktiv:
                return richtlinie
    return await session.scalar(
        select(SlaRichtlinie).where(
            SlaRichtlinie.mandant_id == vorgang.mandant_id,
            SlaRichtlinie.ist_standard.is_(True),
            SlaRichtlinie.aktiv.is_(True),
        )
    )


async def _kalender(session: AsyncSession, vorgang: Vorgang, richtlinie: SlaRichtlinie) -> SlaKalender:
    mandant = await session.get(Mandant, vorgang.mandant_id)
    return kalender_von(richtlinie, mandant.bundesland if mandant else None)


def _offen(vorgang: Vorgang, art: FristArt) -> bool:
    return (vorgang.sla_reagiert_am if art == "reaktion" else vorgang.sla_geloest_am) is None


def _faelligkeiten_setzen(vorgang: Vorgang, richtlinie: SlaRichtlinie, kal: SlaKalender) -> None:
    """Berechnet die Fristen offener Fristarten aus laeuft_seit und verbrauchter Zeit."""
    for art in ("reaktion", "loesung"):
        if not _offen(vorgang, art):
            continue  # erledigte Frist bleibt unveraendert
        ziel = ziel_min(richtlinie, vorgang.prioritaet, art)
        feld = f"sla_{art}_faellig_am"
        if ziel is None or vorgang.sla_laeuft_seit is None:
            setattr(vorgang, feld, None if ziel is None else getattr(vorgang, feld))
            continue
        rest = max(0, ziel - getattr(vorgang, f"sla_{art}_verbraucht_min"))
        setattr(vorgang, feld, add_geschaeftsminuten(vorgang.sla_laeuft_seit, rest, kal))


def _abschnitt_verbuchen(vorgang: Vorgang, kal: SlaKalender, jetzt: datetime) -> None:
    if vorgang.sla_laeuft_seit is None:
        return
    gelaufen = geschaeftsminuten_zwischen(vorgang.sla_laeuft_seit, jetzt, kal)
    for art in ("reaktion", "loesung"):
        if _offen(vorgang, art):
            feld = f"sla_{art}_verbraucht_min"
            setattr(vorgang, feld, getattr(vorgang, feld) + gelaufen)


async def initialisieren(session: AsyncSession, vorgang: Vorgang, *, start: datetime | None = None) -> None:
    """Beim Anlegen: Richtlinie aufloesen, Prioritaetsregel anwenden, Fristen setzen."""
    richtlinie = await richtlinie_aufloesen(session, vorgang)
    if richtlinie is None:
        return
    start = start or _jetzt()
    vorgang.sla_richtlinie_id = richtlinie.id
    vorgang.sla_start_am = start
    vorgang.sla_laeuft_seit = start
    # Regel je Vertrag: hebt nur an, senkt nie (eine bewusst hoeher gesetzte Prioritaet bleibt).
    regel = (richtlinie.prioritaet_regeln or {}).get(vorgang.leistungstyp)
    if regel is not None and regel > vorgang.prioritaet:
        vorgang.prioritaet = regel
    _faelligkeiten_setzen(vorgang, richtlinie, await _kalender(session, vorgang, richtlinie))


async def _laden(session: AsyncSession, vorgang: Vorgang) -> tuple[SlaRichtlinie, SlaKalender] | None:
    if vorgang.sla_richtlinie_id is None:
        return None
    richtlinie = await session.get(SlaRichtlinie, vorgang.sla_richtlinie_id)
    if richtlinie is None:
        return None
    return richtlinie, await _kalender(session, vorgang, richtlinie)


def _ergebnis(faellig: datetime | None, jetzt: datetime) -> str:
    return "verletzt" if faellig is not None and jetzt > faellig else "erfuellt"


def _reaktion_erfassen(vorgang: Vorgang, jetzt: datetime) -> None:
    if vorgang.sla_reagiert_am is None:
        vorgang.sla_reagiert_am = jetzt
        vorgang.sla_reaktion_ergebnis = _ergebnis(vorgang.sla_reaktion_faellig_am, jetzt)


async def mitarbeiter_reaktion(session: AsyncSession, vorgang: Vorgang, *, jetzt: datetime | None = None) -> None:
    """Erste inhaltliche Aktion eines Mitarbeiters (Kommentar, Statuswechsel weg von neu)."""
    if vorgang.sla_richtlinie_id is None or vorgang.sla_reagiert_am is not None:
        return
    _reaktion_erfassen(vorgang, jetzt or _jetzt())


async def status_gewechselt(
    session: AsyncSession, vorgang: Vorgang, alt: str, neu: str, *, jetzt: datetime | None = None
) -> None:
    if alt == neu or vorgang.sla_richtlinie_id is None:
        return
    geladen = await _laden(session, vorgang)
    if geladen is None:
        return
    richtlinie, kal = geladen
    jetzt = jetzt or _jetzt()

    if neu in ABGESCHLOSSEN_STATUS:
        _abschnitt_verbuchen(vorgang, kal, jetzt)
        vorgang.sla_laeuft_seit = None
        if neu != "storniert":
            _reaktion_erfassen(vorgang, jetzt)
            if vorgang.sla_geloest_am is None:
                vorgang.sla_geloest_am = jetzt
                vorgang.sla_loesung_ergebnis = _ergebnis(vorgang.sla_loesung_faellig_am, jetzt)
        return

    if alt == "neu":
        _reaktion_erfassen(vorgang, jetzt)

    if neu == "wartet_kunde":
        _abschnitt_verbuchen(vorgang, kal, jetzt)
        vorgang.sla_laeuft_seit = None
        return

    # Fortsetzen (aus wartet_kunde) bzw. Wiederoeffnen (aus einem Abschlussstatus).
    if alt in ABGESCHLOSSEN_STATUS:
        vorgang.sla_geloest_am = None
        vorgang.sla_loesung_ergebnis = None
    if vorgang.sla_laeuft_seit is None:
        vorgang.sla_laeuft_seit = jetzt
        _faelligkeiten_setzen(vorgang, richtlinie, kal)


async def prioritaet_geaendert(session: AsyncSession, vorgang: Vorgang, *, jetzt: datetime | None = None) -> None:
    """Neue Ziele ab Eingang, abzueglich der bereits verbrauchten Zeit."""
    geladen = await _laden(session, vorgang)
    if geladen is None:
        return
    richtlinie, kal = geladen
    jetzt = jetzt or _jetzt()
    if vorgang.sla_laeuft_seit is not None:
        _abschnitt_verbuchen(vorgang, kal, jetzt)
        vorgang.sla_laeuft_seit = jetzt
    _faelligkeiten_setzen(vorgang, richtlinie, kal)


async def vertrag_geaendert(session: AsyncSession, vorgang: Vorgang, *, jetzt: datetime | None = None) -> None:
    """Richtlinie neu aufloesen; verbrauchte Zeit bleibt, nur die Ziele aendern sich."""
    richtlinie = await richtlinie_aufloesen(session, vorgang)
    if richtlinie is None:
        return
    if vorgang.sla_richtlinie_id is None:
        await initialisieren(session, vorgang, start=vorgang.created_at)
        return
    if richtlinie.id != vorgang.sla_richtlinie_id:
        vorgang.sla_richtlinie_id = richtlinie.id
        await prioritaet_geaendert(session, vorgang, jetzt=jetzt)


def sla_info(vorgang: Vorgang, *, jetzt: datetime | None = None) -> dict | None:
    """Anzeigestatus fuer die API. Reine Funktion auf den Snapshot-Feldern."""
    if vorgang.sla_richtlinie_id is None:
        return None
    jetzt = jetzt or _jetzt()
    info = {
        "reaktion_faellig_am": vorgang.sla_reaktion_faellig_am,
        "loesung_faellig_am": vorgang.sla_loesung_faellig_am,
        "reagiert_am": vorgang.sla_reagiert_am,
        "geloest_am": vorgang.sla_geloest_am,
        "reaktion_ergebnis": vorgang.sla_reaktion_ergebnis,
        "loesung_ergebnis": vorgang.sla_loesung_ergebnis,
    }
    if vorgang.sla_geloest_am is not None:
        verletzt = "verletzt" in (vorgang.sla_reaktion_ergebnis, vorgang.sla_loesung_ergebnis)
        return {**info, "status": "verletzt" if verletzt else "erfuellt"}
    if vorgang.sla_laeuft_seit is None:
        return {**info, "status": "pausiert"}
    offene = [
        f for f, erledigt in (
            (vorgang.sla_reaktion_faellig_am, vorgang.sla_reagiert_am is not None),
            (vorgang.sla_loesung_faellig_am, False),
        )
        if f is not None and not erledigt
    ]
    if vorgang.sla_reaktion_ergebnis == "verletzt":
        return {**info, "status": "verletzt"}
    if not offene:
        return {**info, "status": "ok"}
    if any(jetzt > f for f in offene):
        return {**info, "status": "verletzt"}
    start = vorgang.sla_start_am or vorgang.created_at
    for faellig in offene:
        gesamt = (faellig - start).total_seconds()
        if gesamt > 0 and (jetzt - start).total_seconds() / gesamt >= GEFAEHRDET_AB:
            return {**info, "status": "gefaehrdet"}
    return {**info, "status": "ok"}
