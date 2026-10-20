"""Import rueckgaengig machen: legt die durch den Lauf angelegten Datensaetze in den Papierkorb.

Nur Datensaetze, die seit dem Import unveraendert sind (updated_at == created_at) und an denen
nichts Fremdes haengt, werden zurueckgesetzt -- sonst ginge Arbeit verloren, die jemand darauf
aufgebaut hat. Aktualisierte (nicht angelegte) Datensaetze bleiben unberuehrt; der Papierkorb
stellt Einzelstuecke wie gewohnt wieder her. Vergebene Nummern werden nie zurueckgegeben."""
from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.angebot import Angebot
from app.models.anlage import Anlage
from app.models.auftrag import Auftrag
from app.models.bestellung import BestellungPosition
from app.models.dauerauftrag import Dauerauftrag
from app.models.dauerauftrag_ziel import DauerauftragZiel
from app.models.einladung import Einladung
from app.models.fahrzeug_zuweisung import FahrzeugZuweisung
from app.models.import_lauf import ImportLauf, ImportLaufEintrag
from app.models.inventurzyklus import InventurZyklus
from app.models.kunde import Kunde
from app.models.kunde_zuweisung import KundeZuweisung
from app.models.kundenportal import KundenportalZugang
from app.models.mangel import Mangel
from app.models.material import Material, MaterialBewegung, MaterialVerwendung
from app.models.material_bedarf import MaterialBedarf
from app.models.projekt import Projekt
from app.models.pruefzyklus import Pruefzyklus
from app.models.rechnung import Rechnung, RechnungPosition
from app.models.standort import Standort
from app.models.vertrag import Vertrag
from app.models.vorgang import Vorgang
from app.models.vorgang_anfrage import VorgangAnfrage
from app.models.vorgang_anlage import VorgangAnlage
from app.services import audit_service

# Reihenfolge: Kinder vor Eltern, damit Abhaengige im selben Lauf als "geht mit" zaehlen.
REIHENFOLGE = ("pruefzyklus", "anlage", "standort", "kunde", "material")
MODELLE = {"pruefzyklus": Pruefzyklus, "anlage": Anlage, "standort": Standort, "kunde": Kunde, "material": Material}
_CHARGE = 5000
_MAX_UEBERSPRUNGEN_LISTE = 100


def _abhaengige(typ: str) -> list[tuple[str | None, type, str]]:
    """(Typ im selben Lauf oder None, Modell, FK-Spalte) -- aktive Zeilen daraus blockieren das Zuruecksetzen."""
    if typ == "kunde":
        spezifikation = [
            ("standort", Standort, "kunde_id"), ("anlage", Anlage, "kunde_id"), (None, Vertrag, "kunde_id"),
            (None, Dauerauftrag, "kunde_id"), (None, VorgangAnfrage, "kunde_id"), (None, Vorgang, "kunde_id"),
            (None, Auftrag, "kunde_id"), (None, Rechnung, "kunde_id"), (None, Angebot, "kunde_id"),
            (None, Projekt, "kunde_id"), (None, KundenportalZugang, "kunde_id"), (None, KundeZuweisung, "kunde_id"),
            (None, Einladung, "kunde_id"),
        ]
    elif typ == "standort":
        spezifikation = [
            ("anlage", Anlage, "standort_id"), (None, Vorgang, "standort_id"), (None, VorgangAnfrage, "standort_id"),
            (None, Projekt, "standort_id"),
        ]
    elif typ == "anlage":
        spezifikation = [
            ("pruefzyklus", Pruefzyklus, "anlage_id"), (None, Vertrag, "anlage_id"), (None, Vorgang, "anlage_id"),
            (None, Mangel, "anlage_id"), (None, VorgangAnfrage, "anlage_id"), (None, DauerauftragZiel, "anlage_id"),
            (None, InventurZyklus, "lager_id"), (None, FahrzeugZuweisung, "anlage_id"), (None, VorgangAnlage, "anlage_id"),
            (None, Projekt, "anlage_id"),
        ]
    elif typ == "material":
        spezifikation = [
            (None, MaterialBedarf, "material_id"), (None, BestellungPosition, "material_id"),
            (None, MaterialVerwendung, "material_id"), (None, RechnungPosition, "material_id"),
        ]
    else:
        spezifikation = []
    return [(t, m, a) for t, m, a in spezifikation if hasattr(m, a)]


def _stuecke(ids: list[UUID]):
    for i in range(0, len(ids), _CHARGE):
        yield ids[i : i + _CHARGE]


async def rueckgaengig(session: AsyncSession, lauf: ImportLauf, user_id: UUID) -> dict:
    from app.services.datenimport.lauf import ImportFehler

    if lauf.status != "abgeschlossen":
        raise ImportFehler("Nur abgeschlossene Importläufe können rückgängig gemacht werden.", 409)
    zeilen = (
        await session.execute(
            select(ImportLaufEintrag.entitaet_typ, ImportLaufEintrag.entitaet_id, ImportLaufEintrag.aktion).where(
                ImportLaufEintrag.import_lauf_id == lauf.id
            )
        )
    ).all()
    angelegt: dict[str, list[UUID]] = defaultdict(list)
    aktualisiert = 0
    for typ, eid, aktion in zeilen:
        if aktion == "angelegt":
            angelegt[typ].append(eid)
        else:
            aktualisiert += 1

    entfernt: dict[str, set[UUID]] = {}
    uebersprungen: list[dict] = []
    uebersprungen_gesamt = 0
    bereits_im_papierkorb = 0

    def sperren(typ: str, eid: UUID, grund: str) -> None:
        nonlocal uebersprungen_gesamt
        uebersprungen_gesamt += 1
        if len(uebersprungen) < _MAX_UEBERSPRUNGEN_LISTE:
            uebersprungen.append({"typ": typ, "id": str(eid), "grund": grund})

    for typ in REIHENFOLGE:
        modell = MODELLE[typ]
        kandidaten: dict[UUID, str | None] = {}
        for stueck in _stuecke(angelegt.get(typ, [])):
            rows = (
                await session.execute(
                    select(modell.id, modell.created_at, modell.updated_at, modell.geloescht_am).where(modell.id.in_(stueck))
                )
            ).all()
            for eid, erstellt, geaendert, geloescht in rows:
                if geloescht is not None:
                    bereits_im_papierkorb += 1
                elif geaendert != erstellt:
                    sperren(typ, eid, "seit dem Import geändert")
                else:
                    kandidaten[eid] = None
        gesperrt: set[UUID] = set()
        ids = list(kandidaten)
        for abh_typ, abh_modell, attr in _abhaengige(typ):
            spalte = getattr(abh_modell, attr)
            for stueck in _stuecke(ids):
                stmt = select(abh_modell.id, spalte).where(spalte.in_(stueck))
                if hasattr(abh_modell, "geloescht_am"):
                    stmt = stmt.where(abh_modell.geloescht_am.is_(None))
                for abh_id, eltern_id in (await session.execute(stmt)).all():
                    if abh_typ is not None and abh_id in entfernt.get(abh_typ, set()):
                        continue
                    gesperrt.add(eltern_id)
        if typ == "material":
            gesperrt |= await _material_mit_buchungen(session, ids)
        for eid in gesperrt:
            sperren(typ, eid, "es existieren abhängige Datensätze (z. B. Aufträge, Buchungen)")
        entfernt[typ] = set(ids) - gesperrt

    jetzt = datetime.now(UTC)
    zurueckgesetzt: dict[str, int] = {}
    for typ in REIHENFOLGE:
        ids = list(entfernt.get(typ, ()))
        if not ids:
            continue
        modell = MODELLE[typ]
        for stueck in _stuecke(ids):
            await session.execute(
                update(modell)
                .where(modell.id.in_(stueck), modell.geloescht_am.is_(None))
                .values(geloescht_am=jetzt, geloescht_von=user_id)
                .execution_options(synchronize_session=False)
            )
        zurueckgesetzt[typ] = len(ids)

    ergebnis = {
        "zurueckgesetzt": zurueckgesetzt,
        "uebersprungen_gesamt": uebersprungen_gesamt,
        "uebersprungen": uebersprungen,
        "bereits_im_papierkorb": bereits_im_papierkorb,
        "aktualisierte_nicht_zurueckgesetzt": aktualisiert,
    }
    if zurueckgesetzt or bereits_im_papierkorb:
        lauf.status = "rueckgaengig"
        lauf.rueckgaengig_am = jetzt
    lauf.ergebnis = {**(lauf.ergebnis or {}), "rueckgaengig": ergebnis}
    await audit_service.log_action(
        session,
        aktion="datenimport_rueckgaengig",
        mandant_id=lauf.mandant_id,
        actor_user_id=user_id,
        entity_type="import_lauf",
        entity_id=lauf.id,
        payload={
            "entitaet": lauf.entitaet,
            "zurueckgesetzt": zurueckgesetzt,
            "uebersprungen_gesamt": uebersprungen_gesamt,
        },
    )
    await session.flush()
    return ergebnis


async def _material_mit_buchungen(session: AsyncSession, ids: list[UUID]) -> set[UUID]:
    """Material mit anderen Bewegungen als dem einen Anfangs-Wareneingang des Imports."""
    gesperrt: set[UUID] = set()
    for stueck in _stuecke(ids):
        rows = (
            await session.execute(
                select(MaterialBewegung.material_id)
                .where(MaterialBewegung.material_id.in_(stueck))
                .group_by(MaterialBewegung.material_id)
                .having(
                    (func.count() > 1)
                    | (func.count().filter(MaterialBewegung.typ != "eingang") > 0)
                )
            )
        ).scalars()
        gesperrt |= set(rows)
    return gesperrt
