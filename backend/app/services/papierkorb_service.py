"""Papierkorb: weiches Loeschen/Wiederherstellen/endgueltiges Loeschen fuer
alle "fachlichen" Entitaeten (siehe Migration 0032 fuer die vollstaendige
Begruendung, welche Tabellen bewusst NICHT dabei sind).

soft_delete() loescht kaskadierend -- wird z.B. ein Kunde geloescht, wandern
alle davon abhaengigen Datensaetze (Standorte, Anlagen, Vertraege, Vorgaenge,
...) automatisch mit in den Papierkorb. restore() ist bewusst NICHT
kaskadierend: es stellt ausschliesslich den einen angefragten Datensatz
wieder her, Kinder bleiben geloescht, bis sie einzeln wiederhergestellt
werden. purge() loescht einen bereits weich geloeschten Teilbaum endgueltig
und unwiderruflich (echtes DELETE), Kinder zuerst, damit FK-Constraints nicht
verletzt werden.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.angebot import Angebot
from app.models.anlage import Anlage
from app.models.bestellung import Bestellung
from app.models.dauerauftrag import Dauerauftrag
from app.models.dauerauftrag_ziel import DauerauftragZiel
from app.models.eingangsrechnung import Eingangsrechnung
from app.models.fahrzeug_zuweisung import FahrzeugZuweisung
from app.models.inventurzyklus import InventurZyklus
from app.models.kunde import Kunde
from app.models.leistungsverzeichnis import LeistungsverzeichnisPosition
from app.models.lieferant import Lieferant
from app.models.mangel import Mangel
from app.models.material import Material
from app.models.material_bedarf import MaterialBedarf
from app.models.projekt import Projekt, ProjektAufgabe
from app.models.pruefmittel import Pruefmittel
from app.models.pruefzyklus import Pruefzyklus
from app.models.rechnung import Rechnung
from app.models.standort import Standort
from app.models.tag import Tag
from app.models.termin import Termin
from app.models.vertrag import Vertrag
from app.models.vorgang import Vorgang
from app.models.vorgang_anfrage import VorgangAnfrage


@dataclass(frozen=True)
class EntityKind:
    modell: type
    # Attribut fuer eine sprechende Anzeige im Papierkorb -- None, wenn die
    # Entitaet kein einzelnes gut lesbares Feld hat (dann zeigt das Frontend
    # nur Typ + Kurz-ID).
    titel_feld: str | None
    # (Kind-Entitaetstyp, FK-Attributname am Kind, das auf diese Entitaet
    # zeigt) -- fuer die Kaskade bei soft_delete()/purge().
    kinder: tuple[tuple[str, str], ...] = field(default_factory=tuple)


ENTITY_REGISTRY: dict[str, EntityKind] = {
    "kunde": EntityKind(
        Kunde,
        "name",
        (
            ("standort", "kunde_id"),
            ("vertrag", "kunde_id"),
            ("dauerauftrag", "kunde_id"),
            ("anlage", "kunde_id"),
            ("vorgang_anfrage", "kunde_id"),
            ("vorgang", "kunde_id"),
            ("leistungsverzeichnis_position", "kunde_id"),
        ),
    ),
    "standort": EntityKind(
        Standort,
        "bezeichnung",
        (
            ("anlage", "standort_id"),
            ("vorgang", "standort_id"),
        ),
    ),
    "anlage": EntityKind(
        Anlage,
        "bezeichnung",
        (
            ("vertrag", "anlage_id"),
            ("vorgang", "anlage_id"),
            ("mangel", "anlage_id"),
            ("pruefzyklus", "anlage_id"),
            ("vorgang_anfrage", "anlage_id"),
            ("dauerauftrag_ziel", "anlage_id"),
            ("inventurzyklus", "lager_id"),
            ("fahrzeug_zuweisung", "anlage_id"),
        ),
    ),
    "vertrag": EntityKind(Vertrag, "bezeichnung", (("vorgang", "vertrag_id"),)),
    "vorgang": EntityKind(
        Vorgang,
        "titel",
        (
            ("mangel", "vorgang_id"),
            ("angebot", "vorgang_id"),
            ("rechnung", "vorgang_id"),
            ("eingangsrechnung", "vorgang_id"),
            ("material_bedarf", "vorgang_id"),
            ("termin", "vorgang_id"),
            ("vorgang", "parent_vorgang_id"),
        ),
    ),
    "termin": EntityKind(Termin, "titel"),
    "pruefzyklus": EntityKind(Pruefzyklus, "bezeichnung"),
    "pruefmittel": EntityKind(Pruefmittel, "bezeichnung"),
    "projekt": EntityKind(Projekt, "name", (("projekt_aufgabe", "projekt_id"),)),
    "projekt_aufgabe": EntityKind(ProjektAufgabe, "titel", (("projekt_aufgabe", "eltern_aufgabe_id"),)),
    "lieferant": EntityKind(
        Lieferant, "name", (("bestellung", "lieferant_id"), ("eingangsrechnung", "lieferant_id"))
    ),
    "material": EntityKind(Material, "bezeichnung", (("material_bedarf", "material_id"),)),
    # Verwendungen (Buchungshistorie an Vorgaengen) kaskadieren bewusst
    # nicht mit -- gleiche Regel wie bei material_verwendungen, siehe
    # delete_material in app/api/routes/material.py.
    "leistungsverzeichnis_position": EntityKind(LeistungsverzeichnisPosition, "bezeichnung"),
    "material_bedarf": EntityKind(MaterialBedarf, None),
    "bestellung": EntityKind(Bestellung, "bestellnummer"),
    "dauerauftrag": EntityKind(
        Dauerauftrag, "titel", (("dauerauftrag_ziel", "dauerauftrag_id"),)
    ),
    "dauerauftrag_ziel": EntityKind(DauerauftragZiel, None),
    "mangel": EntityKind(Mangel, "beschreibung"),
    "angebot": EntityKind(Angebot, "angebotsnummer"),
    "rechnung": EntityKind(Rechnung, "rechnungsnummer"),
    "eingangsrechnung": EntityKind(Eingangsrechnung, "rechnungsnummer_lieferant"),
    "inventurzyklus": EntityKind(InventurZyklus, None),
    "fahrzeug_zuweisung": EntityKind(FahrzeugZuweisung, None),
    "tag": EntityKind(Tag, "label"),
    "vorgang_anfrage": EntityKind(VorgangAnfrage, "titel"),
}


class UnbekannterEntityTyp(ValueError):
    pass


class GobdLoeschsperre(Exception):
    """Ein Beleg mit gesetzlicher Aufbewahrungspflicht (§147 AO/§257 HGB,
    10 Jahre) darf nicht endgueltig geloescht werden -- auch dann nicht,
    wenn ein Kunde sein DSGVO-Loeschrecht ausueben moechte: Art. 17 Abs. 3
    lit. b DSGVO nimmt genau diesen Fall (gesetzliche Aufbewahrungspflicht)
    ausdruecklich von der Loeschpflicht aus. Betroffen: jede Eingangsrechnung
    (repraesentiert immer einen tatsaechlich erhaltenen Beleg) sowie jede
    Rechnung ausser im Status "entwurf" (noch nicht versendet, also noch kein
    tatsaechlich ausgestellter Beleg)."""

    def __init__(self, entity_typ: str, entity_id: UUID, beleg_nummer: str | None):
        self.entity_typ = entity_typ
        self.entity_id = entity_id
        self.beleg_nummer = beleg_nummer
        bezeichner = f" ({beleg_nummer})" if beleg_nummer else ""
        super().__init__(
            f"{entity_typ}{bezeichner} unterliegt der GoBD-Aufbewahrungspflicht "
            "und darf nicht endgueltig geloescht werden."
        )


def _kind(entity_typ: str) -> EntityKind:
    try:
        return ENTITY_REGISTRY[entity_typ]
    except KeyError:
        raise UnbekannterEntityTyp(entity_typ) from None


def _gobd_gesperrt(entity_typ: str, obj: Any) -> bool:
    if entity_typ == "eingangsrechnung":
        # "entwurf" = unbestaetigter E-Mail-Import (siehe
        # email_ingest_service.py) -- noch kein echter Geschaeftsvorfall,
        # also (anders als ein bestaetigter Beleg) nicht GoBD-gesperrt.
        return obj.status != "entwurf"
    if entity_typ == "rechnung":
        return obj.status != "entwurf"
    return False


def _beleg_nummer(entity_typ: str, obj: Any) -> str | None:
    kind = _kind(entity_typ)
    return getattr(obj, kind.titel_feld) if kind.titel_feld else None


async def _aktive_kinder(
    session: AsyncSession, *, kind_typ: str, fk_attr: str, parent_id: UUID
) -> list[UUID]:
    kind = _kind(kind_typ)
    spalte = getattr(kind.modell, fk_attr)
    result = await session.execute(
        select(kind.modell.id).where(spalte == parent_id, kind.modell.geloescht_am.is_(None))
    )
    return list(result.scalars().all())


async def _geloeschte_kinder(
    session: AsyncSession, *, kind_typ: str, fk_attr: str, parent_id: UUID
) -> list[UUID]:
    kind = _kind(kind_typ)
    spalte = getattr(kind.modell, fk_attr)
    result = await session.execute(
        select(kind.modell.id).where(
            spalte == parent_id, kind.modell.geloescht_am.is_not(None)
        )
    )
    return list(result.scalars().all())


async def soft_delete(
    session: AsyncSession, *, entity_typ: str, entity_id: UUID, actor_user_id: UUID
) -> Any:
    """Loescht kaskadierend weich. Gibt den obersten (angefragten) Datensatz
    zurueck, oder None, wenn er nicht existiert oder bereits geloescht ist."""
    now = datetime.now(UTC)
    wurzel_kind = _kind(entity_typ)
    wurzel = await session.get(wurzel_kind.modell, entity_id)
    if wurzel is None or wurzel.geloescht_am is not None:
        return None

    besucht: set[tuple[str, UUID]] = set()
    warteschlange: list[tuple[str, UUID]] = [(entity_typ, entity_id)]
    while warteschlange:
        typ, eid = warteschlange.pop()
        if (typ, eid) in besucht:
            continue
        besucht.add((typ, eid))
        kind = _kind(typ)
        # SQLAlchemys Identity-Map liefert fuer (entity_typ, entity_id) exakt
        # dasselbe Python-Objekt wie oben (wurzel) zurueck -- kein Sonderfall
        # noetig.
        obj = await session.get(kind.modell, eid)
        if obj is None or obj.geloescht_am is not None:
            continue
        obj.geloescht_am = now
        obj.geloescht_von = actor_user_id
        for kind_typ, fk_attr in kind.kinder:
            for kind_id in await _aktive_kinder(
                session, kind_typ=kind_typ, fk_attr=fk_attr, parent_id=eid
            ):
                warteschlange.append((kind_typ, kind_id))

    await session.flush()
    return wurzel


async def restore(session: AsyncSession, *, entity_typ: str, entity_id: UUID) -> Any:
    """Stellt ausschliesslich den einen angefragten Datensatz wieder her --
    bewusst NICHT kaskadierend, kaskadierend geloeschte Kinder bleiben
    geloescht, bis sie einzeln wiederhergestellt werden."""
    kind = _kind(entity_typ)
    obj = await session.get(kind.modell, entity_id)
    if obj is None or obj.geloescht_am is None:
        return None
    obj.geloescht_am = None
    obj.geloescht_von = None
    await session.flush()
    return obj


async def purge(session: AsyncSession, *, entity_typ: str, entity_id: UUID) -> bool:
    """Loescht einen bereits weich geloeschten Teilbaum endgueltig (echtes
    DELETE), Kinder zuerst. Kann eine IntegrityError auswerfen, wenn noch ein
    nicht kaskadiertes, lediglich referenzierendes Feld (z.B.
    Vorgang.dauerauftrag_id, Pruefzyklus.offener_vorgang_id) auf den
    Datensatz zeigt -- das faengt die aufrufende Route ab. Wirft
    GobdLoeschsperre (und loescht dabei nichts, auch nicht Geschwister-
    Knoten, die vor dem gesperrten Beleg an der Reihe waren -- die
    aufrufende Route rollt die Transaktion beim Abfangen zurueck), wenn
    irgendein Knoten im Teilbaum ein GoBD-pflichtiger Beleg ist."""
    kind = _kind(entity_typ)
    obj = await session.get(kind.modell, entity_id)
    if obj is None or obj.geloescht_am is None:
        return False

    if _gobd_gesperrt(entity_typ, obj):
        raise GobdLoeschsperre(entity_typ, entity_id, _beleg_nummer(entity_typ, obj))

    for kind_typ, fk_attr in kind.kinder:
        for kind_id in await _geloeschte_kinder(
            session, kind_typ=kind_typ, fk_attr=fk_attr, parent_id=entity_id
        ):
            await purge(session, entity_typ=kind_typ, entity_id=kind_id)

    await session.delete(obj)
    await session.flush()
    return True


@dataclass(frozen=True)
class PapierkorbEintrag:
    entity_typ: str
    id: UUID
    titel: str | None
    geloescht_am: datetime
    geloescht_von: UUID | None


async def list_papierkorb(
    session: AsyncSession, *, mandant_id: UUID, entity_typ: str | None = None
) -> list[PapierkorbEintrag]:
    typen = [entity_typ] if entity_typ else list(ENTITY_REGISTRY.keys())
    eintraege: list[PapierkorbEintrag] = []
    for typ in typen:
        kind = _kind(typ)
        modell = kind.modell
        spalten = [modell.id, modell.geloescht_am, modell.geloescht_von]
        if kind.titel_feld:
            spalten.append(getattr(modell, kind.titel_feld))
        result = await session.execute(
            select(*spalten).where(
                modell.mandant_id == mandant_id, modell.geloescht_am.is_not(None)
            )
        )
        for row in result.all():
            titel = row[3] if kind.titel_feld else None
            eintraege.append(
                PapierkorbEintrag(
                    entity_typ=typ,
                    id=row[0],
                    titel=str(titel) if titel is not None else None,
                    geloescht_am=row[1],
                    geloescht_von=row[2],
                )
            )
    eintraege.sort(key=lambda e: e.geloescht_am, reverse=True)
    return eintraege
