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
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.angebot import Angebot
from app.models.anlage import Anlage
from app.models.auftrag import Auftrag
from app.models.bestellung import Bestellung
from app.models.dauerauftrag import Dauerauftrag
from app.models.dauerauftrag_ziel import DauerauftragZiel
from app.models.eingangsrechnung import Eingangsrechnung
from app.models.fahrzeug_zuweisung import FahrzeugZuweisung
from app.models.inventurzyklus import InventurZyklus
from app.models.kunde import Kunde
from app.models.leistungsverzeichnis import Leistungsverzeichnis, LeistungsverzeichnisPosition
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
from app.models.zeiterfassung import Zeiterfassung
from app.core.zeit import in_lokal
from app.services import s3_aufraeumen_service
from app.services.aufbewahrung_service import aufbewahrung_fuer
from app.services.rechnung_service import (
    material_freigeben_fuer_rechnung,
    material_verweis_loesen,
    material_wieder_sperren_fuer_rechnung,
    zeiterfassung_freigeben_fuer_rechnung,
    zeiterfassung_verweis_loesen,
    zeiterfassung_wieder_sperren_fuer_rechnung,
)


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
            ("auftrag", "kunde_id"),
            # KEIN Cascade-Eintrag fuer leistungsverzeichnis(_position) mehr:
            # ein Leistungsverzeichnis kann mehreren Kunden zugewiesen sein
            # (siehe leistungsverzeichnis_kunden), das Loeschen eines Kunden
            # darf ein ggf. geteiltes LV nicht mitreissen -- nur die
            # Zuordnung wird ueber die echte FK-CASCADE beim physischen
            # Loeschen entfernt (siehe Migration 0075/0079).
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
    # KEIN Cascade-Eintrag fuer vorgang: Vorgang.auftrag_id ist rein
    # referenziell, gleiches Prinzip wie projekt oben (Vorgang.projekt_id
    # wird beim Loeschen eines Projekts ebenfalls nicht mitgerissen).
    "auftrag": EntityKind(Auftrag, "titel"),
    "lieferant": EntityKind(
        Lieferant, "name", (("bestellung", "lieferant_id"), ("eingangsrechnung", "lieferant_id"))
    ),
    "material": EntityKind(Material, "bezeichnung", (("material_bedarf", "material_id"),)),
    # Verwendungen (Buchungshistorie an Vorgaengen) kaskadieren bewusst
    # nicht mit -- gleiche Regel wie bei material_verwendungen, siehe
    # delete_material in app/api/routes/material.py.
    "leistungsverzeichnis": EntityKind(
        Leistungsverzeichnis, "name", (("leistungsverzeichnis_position", "leistungsverzeichnis_id"),)
    ),
    "leistungsverzeichnis_position": EntityKind(
        LeistungsverzeichnisPosition, "bezeichnung", (("leistungsverzeichnis_position", "eltern_position_id"),)
    ),
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
    # Kein titel_feld -- ein Zeiterfassungs-Eintrag hat kein einzelnes gut
    # lesbares Feld (siehe material_bedarf oben fuer dasselbe Muster).
    "zeiterfassung": EntityKind(Zeiterfassung, None),
}


def heute_lokal() -> date:
    return in_lokal(datetime.now(UTC)).date()


class UnbekannterEntityTyp(ValueError):
    pass


class GobdLoeschsperre(Exception):
    """Ein Beleg mit gesetzlicher Aufbewahrungspflicht darf bis zum Ende der Frist nicht
    endgueltig geloescht werden (§ 147 AO, § 257 HGB, § 14b UStG; Fristen und Beginn siehe
    aufbewahrung_service) -- auch dann nicht, wenn ein Kunde sein DSGVO-Loeschrecht
    ausueben moechte: Art. 17 Abs. 3 lit. b DSGVO nimmt genau diesen Fall (gesetzliche
    Aufbewahrungspflicht) von der Loeschpflicht aus; der Datensatz bleibt gesperrt im
    Papierkorb, bis die Frist abgelaufen ist. Betroffen: Eingangsrechnungen und
    Rechnungen ausser im Status "entwurf" (noch kein ausgestellter Beleg) sowie
    versendete Angebote (Geschaeftsbriefe)."""

    def __init__(
        self,
        entity_typ: str,
        entity_id: UUID,
        beleg_nummer: str | None,
        fristende: date | None = None,
    ):
        self.entity_typ = entity_typ
        self.entity_id = entity_id
        self.beleg_nummer = beleg_nummer
        self.fristende = fristende
        bezeichner = f" ({beleg_nummer})" if beleg_nummer else ""
        bis = f" bis {fristende:%d.%m.%Y}" if fristende else ""
        super().__init__(
            f"{entity_typ}{bezeichner} unterliegt der GoBD-Aufbewahrungspflicht{bis} "
            "und darf nicht endgueltig geloescht werden."
        )


def _kind(entity_typ: str) -> EntityKind:
    try:
        return ENTITY_REGISTRY[entity_typ]
    except KeyError:
        raise UnbekannterEntityTyp(entity_typ) from None


def _gobd_fristende(entity_typ: str, obj: Any, heute: date) -> date | None:
    """Fristende, wenn der Datensatz noch aufbewahrt werden muss; sonst None (kein Beleg,
    Entwurf oder Frist abgelaufen)."""
    aufbewahrung = aufbewahrung_fuer(entity_typ, obj)
    if aufbewahrung is None or aufbewahrung.abgelaufen(heute):
        return None
    return aufbewahrung.fristende


def _beleg_nummer(entity_typ: str, obj: Any) -> str | None:
    kind = _kind(entity_typ)
    return getattr(obj, kind.titel_feld) if kind.titel_feld else None


async def loesch_protokolldaten(session: AsyncSession, *, entity_typ: str, entity_id: UUID) -> dict:
    """Fuers Protokoll vor dem endgueltigen Loeschen: Belegnummer und, bei Belegen mit
    Aufbewahrungspflicht, Belegart und (abgelaufenes) Fristende."""
    obj = await session.get(_kind(entity_typ).modell, entity_id)
    if obj is None:
        return {}
    daten: dict = {}
    nummer = _beleg_nummer(entity_typ, obj)
    if nummer:
        daten["beleg_nummer"] = nummer
    aufbewahrung = aufbewahrung_fuer(entity_typ, obj)
    if aufbewahrung is not None:
        daten["gobd_belegart"] = aufbewahrung.belegart
        daten["fristende"] = aufbewahrung.fristende.isoformat()
    return daten


async def _pruefe_belege_des_kunden(session: AsyncSession, kunde_id: UUID, heute: date) -> None:
    """Rechnungen und Angebote verweisen auf den Kunden, haengen aber nicht im Kaskadenbaum
    (kinder). Ohne diese Pruefung scheiterte das Loeschen eines Kunden mit Belegen nur an der
    Fremdschluessel-Verletzung -- mit der unverstaendlichen Meldung "andere Daten verweisen
    darauf" statt mit dem Hinweis auf die Aufbewahrungspflicht (DSGVO Art. 17 Abs. 3 lit. b)."""
    for typ in ("rechnung", "angebot"):
        modell = _kind(typ).modell
        belege = (await session.execute(select(modell).where(modell.kunde_id == kunde_id))).scalars()
        for beleg in belege:
            fristende = _gobd_fristende(typ, beleg, heute)
            if fristende is not None:
                raise GobdLoeschsperre(typ, beleg.id, _beleg_nummer(typ, beleg), fristende)


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
        if typ == "rechnung" and obj.status == "entwurf":
            # Auch bei kaskadierendem Loeschen (Vorgang/Kunde): ein Entwurf im
            # Papierkorb soll keine Stunden blockieren. Der Verweis bleibt fuers
            # Wiederherstellen erhalten.
            await zeiterfassung_freigeben_fuer_rechnung(
                session, rechnung_id=eid, geaendert_von=actor_user_id, verweis_behalten=True
            )
            await material_freigeben_fuer_rechnung(session, rechnung_id=eid, verweis_behalten=True)
        for kind_typ, fk_attr in kind.kinder:
            for kind_id in await _aktive_kinder(
                session, kind_typ=kind_typ, fk_attr=fk_attr, parent_id=eid
            ):
                warteschlange.append((kind_typ, kind_id))

    await session.flush()
    return wurzel


async def restore(
    session: AsyncSession, *, entity_typ: str, entity_id: UUID, actor_user_id: UUID | None = None
) -> Any:
    """Stellt ausschliesslich den einen angefragten Datensatz wieder her --
    bewusst NICHT kaskadierend, kaskadierend geloeschte Kinder bleiben
    geloescht, bis sie einzeln wiederhergestellt werden."""
    kind = _kind(entity_typ)
    obj = await session.get(kind.modell, entity_id)
    if obj is None or obj.geloescht_am is None:
        return None
    obj.geloescht_am = None
    obj.geloescht_von = None
    if entity_typ == "rechnung":
        await zeiterfassung_wieder_sperren_fuer_rechnung(
            session, rechnung_id=entity_id, geaendert_von=actor_user_id
        )
        await material_wieder_sperren_fuer_rechnung(session, rechnung_id=entity_id)
    await session.flush()
    return obj


async def purge(
    session: AsyncSession, *, entity_typ: str, entity_id: UUID, heute: date | None = None
) -> bool:
    """Loescht einen bereits weich geloeschten Teilbaum endgueltig (echtes
    DELETE), Kinder zuerst. Kann eine IntegrityError auswerfen, wenn noch ein
    nicht kaskadiertes, lediglich referenzierendes Feld (z.B.
    Vorgang.dauerauftrag_id, Pruefzyklus.offener_vorgang_id) auf den
    Datensatz zeigt -- das faengt die aufrufende Route ab. Wirft
    GobdLoeschsperre (und loescht dabei nichts, auch nicht Geschwister-
    Knoten, die vor dem gesperrten Beleg an der Reihe waren -- die
    aufrufende Route rollt die Transaktion beim Abfangen zurueck), wenn
    irgendein Knoten im Teilbaum ein Beleg ist, dessen Aufbewahrungsfrist noch laeuft.
    Objekte im Objektspeicher werden nicht hier, sondern ueber einen in derselben
    Transaktion vorgemerkten Auftrag nach dem COMMIT entfernt (s3_aufraeumen_service)."""
    kind = _kind(entity_typ)
    obj = await session.get(kind.modell, entity_id)
    if obj is None or obj.geloescht_am is None:
        return False
    heute = heute or heute_lokal()

    fristende = _gobd_fristende(entity_typ, obj, heute)
    if fristende is not None:
        raise GobdLoeschsperre(entity_typ, entity_id, _beleg_nummer(entity_typ, obj), fristende)
    if entity_typ == "kunde":
        await _pruefe_belege_des_kunden(session, entity_id, heute)

    for kind_typ, fk_attr in kind.kinder:
        for kind_id in await _geloeschte_kinder(
            session, kind_typ=kind_typ, fk_attr=fk_attr, parent_id=entity_id
        ):
            await purge(session, entity_typ=kind_typ, entity_id=kind_id, heute=heute)

    if entity_typ == "rechnung":
        await zeiterfassung_verweis_loesen(session, rechnung_id=entity_id)
        await material_verweis_loesen(session, rechnung_id=entity_id)
    if aufbewahrung_fuer(entity_typ, obj) is not None:
        # Abgelaufene Frist: der DB-Trigger gegen das Loeschen festgeschriebener
        # Rechnungen laesst genau dieses Loeschen (nur in dieser Transaktion) zu.
        await session.execute(text("SELECT set_config('app.gobd_loeschfreigabe', 'true', true)"))
    mandant_id = obj.mandant_id
    await session.delete(obj)
    await session.flush()
    await s3_aufraeumen_service.vormerken(
        session, mandant_id=mandant_id, entity_typ=entity_typ, entity_id=entity_id
    )
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
