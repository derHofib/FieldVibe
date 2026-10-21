"""Aufbewahrungsfristen nach Belegart (AO, HGB, UStG).

Stand nach dem Vierten Buerokratieentlastungsgesetz (BEG IV, in Kraft seit
01.01.2025): Buchungsbelege und Rechnungen 8 Jahre (§ 147 Abs. 1 Nr. 4/4a,
Abs. 3 AO, § 257 Abs. 4 HGB, § 14b UStG), Handels- und Geschaeftsbriefe
6 Jahre, Buecher/Jahresabschluesse 10 Jahre. Die Frist beginnt mit dem Ende des
Kalenderjahres, in dem der Beleg entstanden ist (§ 147 Abs. 4 AO) -- das Fristende
ist also immer ein 31. Dezember.

Uebergang (Art. 97 § 19a EGAO): die kuerzere Frist gilt fuer Unterlagen, deren
bisherige 10-Jahres-Frist am 01.01.2025 noch nicht abgelaufen war. Fuer
Rechnungen/Buchungsbelege aus 2014 und frueher blieb es bei 10 Jahren (diese
Fristen waren zum 31.12.2024 ohnehin vorbei), ab Belegjahr 2015 gelten 8 Jahre.

Nicht abgebildet: die Ablaufhemmung nach § 147 Abs. 3 Satz 5 AO (Frist endet
nicht, solange die Unterlagen fuer eine laufende Pruefung/ein Verfahren
gebraucht werden) -- das entscheidet der Betrieb mit seinem Steuerberater."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from app.core.zeit import in_lokal

# Belegart -> Jahre (Regelfrist ab 01.01.2025).
AUFBEWAHRUNG_JAHRE: dict[str, int] = {
    "buchungsbeleg": 8,
    "rechnung": 8,
    "geschaeftsbrief": 6,
    "angebot": 6,
    "buch_jahresabschluss": 10,
}

BELEGART_LABEL: dict[str, str] = {
    "buchungsbeleg": "Buchungsbeleg",
    "rechnung": "Rechnung",
    "geschaeftsbrief": "Handels-/Geschäftsbrief",
    "angebot": "Angebot (Geschäftsbrief)",
    "buch_jahresabschluss": "Buch/Jahresabschluss",
}

# Belegarten, fuer die vor dem BEG IV 10 Jahre galten.
_VORMALS_ZEHN_JAHRE = frozenset({"buchungsbeleg", "rechnung"})
_BEG_IV_STICHTAG = date(2025, 1, 1)
_ALTE_FRIST_JAHRE = 10


def aufbewahrungsjahre(belegart: str, entstehung: date) -> int:
    jahre = AUFBEWAHRUNG_JAHRE[belegart]
    if belegart in _VORMALS_ZEHN_JAHRE:
        alt_ende = date(entstehung.year + _ALTE_FRIST_JAHRE, 12, 31)
        if alt_ende < _BEG_IV_STICHTAG:
            return _ALTE_FRIST_JAHRE
    return jahre


def fristende(belegart: str, entstehung: date) -> date:
    """Letzter Tag der Aufbewahrungspflicht (31.12.). Geloescht werden darf frueher
    als am Folgetag nicht."""
    return date(entstehung.year + aufbewahrungsjahre(belegart, entstehung), 12, 31)


def ist_abgelaufen(ende: date, heute: date) -> bool:
    return heute > ende


@dataclass(frozen=True)
class Aufbewahrung:
    belegart: str
    entstehung: date
    fristende: date

    def abgelaufen(self, heute: date) -> bool:
        return ist_abgelaufen(self.fristende, heute)


def _tag(zeitpunkt: datetime | date) -> date:
    if isinstance(zeitpunkt, datetime):
        return in_lokal(zeitpunkt).date()
    return zeitpunkt


def aufbewahrung_fuer(entity_typ: str, obj: Any) -> Aufbewahrung | None:
    """None = unterliegt (noch) keiner Aufbewahrungspflicht (Entwurf/kein Beleg).
    Entstehung: Ausstellungstag (Versand), bei Eingangsrechnungen der Eingang."""
    if entity_typ == "rechnung":
        if obj.status == "entwurf":
            return None
        quelle = obj.versendet_am or obj.created_at
        beleg = "rechnung"
    elif entity_typ == "eingangsrechnung":
        # "entwurf" = unbestaetigter E-Mail-Import, noch kein Geschaeftsvorfall.
        if obj.status == "entwurf":
            return None
        quelle = obj.eingegangen_am or obj.rechnungsdatum
        beleg = "rechnung"
    elif entity_typ == "angebot":
        if obj.status == "entwurf":
            return None
        quelle = obj.versendet_am or obj.created_at
        beleg = "angebot"
    else:
        return None
    tag = _tag(quelle)
    return Aufbewahrung(beleg, tag, fristende(beleg, tag))


@dataclass(frozen=True)
class Loeschvorschlag:
    entity_typ: str
    id: UUID
    beleg_nummer: str | None
    belegart: str
    fristende: date
    im_papierkorb: bool


async def loeschvorschlaege(session, *, heute: date, limit: int, offset: int) -> tuple[list[Loeschvorschlag], int]:
    """Belege mit abgelaufener Aufbewahrungsfrist (Rechnungen, Eingangsrechnungen, Angebote).
    Nur eine Liste -- geloescht wird nichts ohne Bestaetigung (siehe /api/aufbewahrung)."""
    from sqlalchemy import func, select

    from app.models.angebot import Angebot
    from app.models.eingangsrechnung import Eingangsrechnung
    from app.models.rechnung import Rechnung

    # Grober Vorfilter nach Ausstellungsdatum (Betriebszeitzone vernachlaessigt: eine
    # Obermenge genuegt); die genaue Pruefung macht aufbewahrung_fuer.
    grenze_8 = date(heute.year - 8, 1, 1)
    grenze_6 = date(heute.year - 6, 1, 1)
    zeit_8 = datetime(grenze_8.year, 1, 1, tzinfo=timezone.utc)
    zeit_6 = datetime(grenze_6.year, 1, 1, tzinfo=timezone.utc)
    kandidaten = [
        ("rechnung", Rechnung.rechnungsnummer, select(Rechnung).where(Rechnung.status != "entwurf", func.coalesce(Rechnung.versendet_am, Rechnung.created_at) < zeit_8)),
        (
            "eingangsrechnung",
            Eingangsrechnung.rechnungsnummer_lieferant,
            select(Eingangsrechnung).where(Eingangsrechnung.status != "entwurf", Eingangsrechnung.eingegangen_am < grenze_8),
        ),
        ("angebot", Angebot.angebotsnummer, select(Angebot).where(Angebot.status != "entwurf", func.coalesce(Angebot.versendet_am, Angebot.created_at) < zeit_6)),
    ]
    alle: list[Loeschvorschlag] = []
    for typ, nummer_spalte, stmt in kandidaten:
        for obj in (await session.execute(stmt)).scalars():
            auf = aufbewahrung_fuer(typ, obj)
            if auf is not None and auf.abgelaufen(heute):
                alle.append(
                    Loeschvorschlag(typ, obj.id, getattr(obj, nummer_spalte.key), auf.belegart, auf.fristende, obj.geloescht_am is not None)
                )
    alle.sort(key=lambda v: (v.fristende, v.entity_typ, v.beleg_nummer or ""))
    return alle[offset : offset + limit], len(alle)
