"""Ablauf eines Datenimports: Analyse, Probelauf, Ausfuehren, Fehlerbericht, Aufraeumen.

Zustandslos zwischen den Schritten: die Quelldatei liegt (SSE-S3-verschluesselt) unter dem
Mandantenpraefix im Objektspeicher, jeder Schritt liest sie neu. Probelauf und Import nutzen
dieselbe Pruefung (Verarbeiter.pruefen); der Import schreibt nur, was die Pruefung vorbereitet hat."""
import hashlib
import logging
import re
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from itertools import islice
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.db.session import system_session
from app.models.import_lauf import ImportLauf, ImportLaufEintrag
from app.models.mandant import Mandant
from app.services import audit_service, csv_service, storage_service
from app.services.datenimport.anlagen import AnlagenVerarbeiter
from app.services.datenimport.basis import (
    CHARGE_MAX,
    CHARGE_MIN,
    MODI,
    ImportZeitlimit,
    Konfiguration,
    Kontext,
    ZeilenErgebnis,
)
from app.services.datenimport.felder import EntitaetDef, entitaet as entitaet_def
from app.services.datenimport.kunden import KundenVerarbeiter
from app.services.datenimport.material import MaterialVerarbeiter
from app.services.datenimport.parser import ImportDateiFehler, Limits, Tabelle, lese_tabelle

logger = logging.getLogger(__name__)

VERARBEITER = {
    "kunden": KundenVerarbeiter(),
    "anlagen": AnlagenVerarbeiter(),
    "material": MaterialVerarbeiter(),
}
# Antwortzeilen je Status (der volle Bericht steht im Fehlerbericht-CSV).
ANTWORT_ZEILEN_JE_STATUS = {"fehler": 500, "dublette": 500, "warnung": 300, "neu": 100}
PROBELAUF_ERLAUBT = ("analysiert", "geprueft", "abgebrochen")
AUSFUEHREN_ERLAUBT = ("geprueft", "abgebrochen")
MAX_BEISPIELE = 3


class ImportFehler(Exception):
    def __init__(self, meldung: str, status_code: int = 422):
        super().__init__(meldung)
        self.meldung = meldung
        self.status_code = status_code


def limits() -> Limits:
    s = get_settings()
    return Limits(
        max_bytes=s.import_max_bytes,
        max_zeilen=s.import_max_zeilen,
        max_spalten=s.import_max_spalten,
        max_zellenlaenge=s.import_max_zellenlaenge,
        max_unkomprimiert=s.import_max_entpackt_bytes,
        zeitlimit_sekunden=s.import_zeitlimit_sekunden,
    )


def anzeigename(dateiname: str | None) -> str:
    """Nur der Basisname, ohne Pfadanteile und Steuerzeichen; dient ausschliesslich der Anzeige."""
    name = re.split(r"[\\/]", dateiname or "")[-1]
    name = re.sub(r"[\x00-\x1f\x7f-\x9f​-‏‪-‮]", "", name).strip()
    return (name[:120] or "import")


def definition_von(entitaet: str) -> EntitaetDef:
    definition = entitaet_def(entitaet)
    if definition is None:
        raise ImportFehler("Unbekannter Importtyp.", 404)
    return definition


def modul_aktiv(mandant: Mandant, definition: EntitaetDef) -> bool:
    return definition.modul not in set(mandant.deaktivierte_module)


# --- Analyse -----------------------------------------------------------------


def spalten_info(tabelle: Tabelle) -> list[dict]:
    info = []
    for index, name in enumerate(tabelle.kopf):
        beispiele: list[str] = []
        for zeile in tabelle.zeilen:
            wert = zeile[index] if index < len(zeile) else ""
            if wert and wert not in beispiele:
                beispiele.append(wert[:60])
                if len(beispiele) >= MAX_BEISPIELE:
                    break
        info.append({"index": index, "name": name, "beispiele": beispiele})
    return info


async def analysiere(
    session: AsyncSession,
    *,
    mandant_id: UUID,
    user_id: UUID,
    entitaet: str,
    dateiname: str,
    daten: bytes,
    blatt: str | None,
) -> tuple[ImportLauf, Tabelle]:
    try:
        tabelle = await run_in_threadpool(lese_tabelle, daten, dateiname or "", limits(), blatt=blatt)
    except ImportDateiFehler as exc:
        raise ImportFehler(str(exc), exc.status_code) from None
    lauf_id = uuid4()
    key = storage_service.new_import_quelle_key(mandant_id, lauf_id)
    await storage_service.upload_bytes(key, daten, "application/octet-stream")
    lauf = ImportLauf(
        id=lauf_id,
        mandant_id=mandant_id,
        entitaet=entitaet,
        dateiname=anzeigename(dateiname),
        sha256=hashlib.sha256(daten).hexdigest(),
        dateigroesse=len(daten),
        format=tabelle.format,
        trennzeichen=tabelle.trennzeichen,
        kodierung=tabelle.kodierung,
        blatt=tabelle.blatt,
        status="analysiert",
        zeilen_gesamt=len(tabelle.zeilen),
        spalten=list(tabelle.kopf),
        object_key=key,
        erstellt_von=user_id,
    )
    session.add(lauf)
    await session.flush()
    return lauf, tabelle


async def lade_tabelle(lauf: ImportLauf) -> Tabelle:
    if not lauf.object_key:
        raise ImportFehler("Die hochgeladene Datei wurde bereits entfernt. Bitte die Datei erneut hochladen.", 410)
    try:
        daten = await storage_service.download_bytes(lauf.object_key)
    except Exception:
        logger.warning("Importdatei zu Lauf %s nicht lesbar", lauf.id)
        raise ImportFehler("Die hochgeladene Datei ist nicht mehr verfügbar. Bitte erneut hochladen.", 410) from None
    try:
        return await run_in_threadpool(lese_tabelle, daten, lauf.dateiname, limits(), blatt=lauf.blatt)
    except ImportDateiFehler as exc:
        raise ImportFehler(str(exc), exc.status_code) from None


# --- Konfiguration ---------------------------------------------------------------


def pruefe_konfiguration(definition: EntitaetDef, spaltenzahl: int, konfig: Konfiguration) -> None:
    if konfig.modus not in MODI:
        raise ImportFehler("Unbekannter Importmodus.")
    if not CHARGE_MIN <= konfig.chargengroesse <= CHARGE_MAX:
        raise ImportFehler(f"Die Chargengröße muss zwischen {CHARGE_MIN} und {CHARGE_MAX} liegen.")
    felder = {f.key for f in definition.felder}
    benutzt: dict[int, str] = {}
    for feld, spalte in konfig.mapping.items():
        if feld not in felder:
            raise ImportFehler("Die Zuordnung enthält ein unbekanntes Feld.")
        if spalte is None:
            continue
        if not 0 <= spalte < spaltenzahl:
            raise ImportFehler("Die Zuordnung verweist auf eine Spalte, die in der Datei nicht existiert.")
        if spalte in benutzt:
            raise ImportFehler("Eine Spalte kann nur einem Feld zugeordnet werden.")
        benutzt[spalte] = feld
    for gruppe in definition.pflicht_gruppen:
        if not any(konfig.mapping.get(f) is not None for f in gruppe):
            raise ImportFehler(definition.pflicht_hinweis or "Pflichtfelder sind nicht zugeordnet.")
    arten = {a.key: a for a in definition.dubletten_arten}
    for art, aktion in konfig.dubletten_aktionen.items():
        if art not in arten:
            raise ImportFehler("Die Dublettenregeln enthalten eine unbekannte Art.")
        if aktion not in arten[art].aktionen:
            raise ImportFehler(f"Für „{arten[art].label}“ ist diese Aktion nicht möglich.")


# --- Pruefen / Zusammenfassen ------------------------------------------------


async def _kontext(session: AsyncSession, lauf: ImportLauf, user_id: UUID) -> Kontext:
    mandant = await session.get(Mandant, lauf.mandant_id)
    return Kontext(
        session=session,
        mandant_id=lauf.mandant_id,
        user_id=user_id,
        mandant=mandant,
        frist=time.monotonic() + get_settings().import_zeitlimit_sekunden,
    )


def fasse_zusammen(ergebnisse: list[ZeilenErgebnis]) -> dict:
    status = Counter(e.status for e in ergebnisse)
    aktion = Counter(e.aktion for e in ergebnisse if e.status != "fehler")
    return {
        "gesamt": len(ergebnisse),
        "neu": status["neu"],
        "warnung": status["warnung"],
        "dublette": status["dublette"],
        "fehler": status["fehler"],
        "anlegen": aktion["anlegen"],
        "aktualisieren": aktion["aktualisieren"],
        "ueberspringen": aktion["ueberspringen"],
    }


def antwort_zeilen(ergebnisse: list[ZeilenErgebnis]) -> tuple[list[ZeilenErgebnis], bool]:
    """Auswahl fuer die API-Antwort: je Status begrenzt, in Dateireihenfolge."""
    zaehler: Counter = Counter()
    auswahl, gekuerzt = [], False
    for e in ergebnisse:
        zaehler[e.status] += 1
        if zaehler[e.status] <= ANTWORT_ZEILEN_JE_STATUS[e.status]:
            auswahl.append(e)
        else:
            gekuerzt = True
    return auswahl, gekuerzt


async def probelauf(
    session: AsyncSession, lauf: ImportLauf, konfig: Konfiguration, user_id: UUID
) -> tuple[list[ZeilenErgebnis], dict]:
    if lauf.status not in PROBELAUF_ERLAUBT:
        raise ImportFehler("Für diesen Importlauf ist kein Probelauf mehr möglich.", 409)
    definition = definition_von(lauf.entitaet)
    tabelle = await lade_tabelle(lauf)
    pruefe_konfiguration(definition, len(tabelle.kopf), konfig)
    ergebnisse = await _pruefen(session, lauf, tabelle, konfig, user_id)
    zusammenfassung = fasse_zusammen(ergebnisse)
    lauf.mapping = konfig.als_dict()["mapping"]
    lauf.optionen = {
        "modus": konfig.modus,
        "chargengroesse": konfig.chargengroesse,
        "dubletten_aktionen": dict(konfig.dubletten_aktionen),
    }
    lauf.konfig_hash = konfig.hash()
    lauf.status = "geprueft"
    lauf.geprueft_am = datetime.now(UTC)
    lauf.ergebnis = {**(lauf.ergebnis or {}), "probelauf": zusammenfassung}
    _zaehler_setzen(lauf, zusammenfassung)
    await session.flush()
    return ergebnisse, zusammenfassung


async def _pruefen(session, lauf, tabelle, konfig, user_id) -> list[ZeilenErgebnis]:
    kontext = await _kontext(session, lauf, user_id)
    try:
        return await VERARBEITER[lauf.entitaet].pruefen(kontext, tabelle, konfig)
    except ImportZeitlimit:
        raise ImportFehler("Die Prüfung hat das Zeitlimit überschritten. Bitte die Datei in kleinere Teile aufteilen.", 408) from None


def _zaehler_setzen(lauf: ImportLauf, z: dict) -> None:
    lauf.zeilen_gesamt = z["gesamt"]
    lauf.zeilen_neu = z["anlegen"]
    lauf.zeilen_aktualisiert = z["aktualisieren"]
    lauf.zeilen_uebersprungen = z["ueberspringen"]
    lauf.zeilen_fehler = z["fehler"]
    lauf.zeilen_warnungen = z["warnung"]


# --- Ausfuehren -----------------------------------------------------------------


class _Abbruch(Exception):
    pass


def _db_meldung(exc: DBAPIError) -> str:
    text = str(exc.orig)
    if "uq_kunden_mandant_kundennummer" in text:
        return "Kundennummer ist bereits vergeben"
    if "uq_kunden_mandant_debitorenkonto" in text:
        return "Debitorenkonto ist bereits vergeben"
    return "Die Zeile konnte nicht gespeichert werden (Datenbankfehler)"


def _chargen(zeilen: list[ZeilenErgebnis], groesse: int):
    iterator = iter(zeilen)
    while charge := list(islice(iterator, groesse)):
        yield charge


async def _charge_schreiben(verarbeiter, kontext: Kontext, lauf: ImportLauf, charge: list[ZeilenErgebnis]) -> None:
    session = kontext.session
    async with session.begin_nested():
        eintraege = await verarbeiter.schreiben(kontext, charge)
        session.add_all(
            ImportLaufEintrag(
                mandant_id=lauf.mandant_id, import_lauf_id=lauf.id, entitaet_typ=typ, entitaet_id=eid,
                aktion=aktion, zeile=nr,
            )
            for typ, eid, aktion, nr in eintraege
        )
        await session.flush()


async def ausfuehren(
    session: AsyncSession, lauf: ImportLauf, konfig: Konfiguration, user_id: UUID
) -> tuple[list[ZeilenErgebnis], dict, Tabelle]:
    if lauf.status not in AUSFUEHREN_ERLAUBT:
        if lauf.status == "analysiert":
            raise ImportFehler("Bitte zuerst einen Probelauf durchführen.", 409)
        raise ImportFehler("Dieser Importlauf wurde bereits abgeschlossen.", 409)
    definition = definition_von(lauf.entitaet)
    if lauf.konfig_hash != konfig.hash():
        raise ImportFehler(
            "Zuordnung oder Optionen wurden seit dem Probelauf geändert. Bitte den Probelauf erneut durchführen.", 409
        )
    tabelle = await lade_tabelle(lauf)
    pruefe_konfiguration(definition, len(tabelle.kopf), konfig)
    verarbeiter = VERARBEITER[lauf.entitaet]
    kontext = await _kontext(session, lauf, user_id)
    lauf.ausgefuehrt_am = datetime.now(UTC)
    try:
        ergebnisse = await verarbeiter.pruefen(kontext, tabelle, konfig)
    except ImportZeitlimit:
        raise ImportFehler("Die Prüfung hat das Zeitlimit überschritten. Bitte die Datei in kleinere Teile aufteilen.", 408) from None

    abgebrochen_grund = None
    if konfig.modus == "alles_oder_nichts" and any(e.status == "fehler" for e in ergebnisse):
        abgebrochen_grund = "Die Datei enthält fehlerhafte Zeilen; im Modus „alles oder nichts“ wurde nichts importiert."
    else:
        try:
            await _schreiben(verarbeiter, kontext, lauf, konfig, ergebnisse)
        except ImportZeitlimit:
            raise ImportFehler(
                "Der Import hat das Zeitlimit überschritten und wurde vollständig zurückgenommen. "
                "Bitte die Datei in kleinere Teile aufteilen.", 408,
            ) from None
        except _Abbruch as exc:
            abgebrochen_grund = str(exc)
            # Nichts wurde geschrieben: die Zeilen gelten wieder als nur geprueft.
            for e in ergebnisse:
                if e.status != "fehler":
                    e.meldungen.append("Nicht importiert (Abbruch im Modus „alles oder nichts“)")

    zusammenfassung = fasse_zusammen(ergebnisse)
    if abgebrochen_grund:
        zusammenfassung = {**zusammenfassung, "anlegen": 0, "aktualisieren": 0}
        lauf.status = "abgebrochen"
    else:
        lauf.status = "abgeschlossen"
        lauf.abgeschlossen_am = datetime.now(UTC)
    _zaehler_setzen(lauf, zusammenfassung)
    lauf.ergebnis = {
        **(lauf.ergebnis or {}),
        "ausfuehrung": zusammenfassung,
        **({"abbruch": abgebrochen_grund} if abgebrochen_grund else {}),
    }
    await _fehlerbericht_ablegen(lauf, tabelle, ergebnisse)
    if lauf.status == "abgeschlossen":
        await _quelle_entfernen(lauf)
    await audit_service.log_action(
        session,
        aktion="datenimport_ausgefuehrt" if not abgebrochen_grund else "datenimport_abgebrochen",
        mandant_id=lauf.mandant_id,
        actor_user_id=user_id,
        entity_type="import_lauf",
        entity_id=lauf.id,
        payload={"entitaet": lauf.entitaet, "sha256": lauf.sha256, **zusammenfassung},
    )
    await session.flush()
    return ergebnisse, zusammenfassung, tabelle


async def _schreiben(verarbeiter, kontext: Kontext, lauf: ImportLauf, konfig: Konfiguration, ergebnisse) -> None:
    session = kontext.session
    zu_schreiben = [e for e in ergebnisse if e.wird_geschrieben]
    if not zu_schreiben:
        return
    # Aeusserer Sicherungspunkt: Zeitlimit und "alles oder nichts" nehmen alles zurueck, was
    # bis dahin geschrieben wurde -- auch den hochgezaehlten Nummernkreis.
    async with session.begin_nested():
        await verarbeiter.vorbereiten_schreiben(kontext, zu_schreiben)
        for charge in _chargen(zu_schreiben, konfig.chargengroesse):
            kontext.frist_pruefen()
            try:
                await _charge_schreiben(verarbeiter, kontext, lauf, charge)
            except DBAPIError as exc:
                if konfig.modus == "alles_oder_nichts":
                    raise _Abbruch(f"{_db_meldung(exc)}; im Modus „alles oder nichts“ wurde nichts importiert.") from None
                # Eine Zeile der Charge ist schuld: einzeln wiederholen, damit nur sie als Fehler zaehlt.
                for zeile in charge:
                    try:
                        await _charge_schreiben(verarbeiter, kontext, lauf, [zeile])
                    except DBAPIError as einzel:
                        zeile.fehler(_db_meldung(einzel))


# --- Fehlerbericht ------------------------------------------------------------


def fehlerbericht_bytes(
    tabelle: Tabelle, ergebnisse: list[ZeilenErgebnis], arten: tuple[str, ...] = ("fehler",)
) -> bytes:
    nach_nr = {nr: zellen for nr, zellen in zip(tabelle.zeilennummern, tabelle.zeilen)}
    kopf = ["Zeile", "Status", "Meldung", *tabelle.kopf]
    zeilen = []
    for e in ergebnisse:
        if e.status not in arten:
            continue
        zeilen.append([e.nr, e.status, " | ".join(e.meldungen), *nach_nr.get(e.nr, [])])
    return csv_service.csv_bytes(kopf, zeilen, formelschutz=True)


async def _fehlerbericht_ablegen(lauf: ImportLauf, tabelle: Tabelle, ergebnisse: list[ZeilenErgebnis]) -> None:
    if not any(e.status == "fehler" for e in ergebnisse):
        return
    inhalt = await run_in_threadpool(fehlerbericht_bytes, tabelle, ergebnisse)
    key = storage_service.new_import_fehlerbericht_key(lauf.mandant_id, lauf.id)
    await storage_service.upload_bytes(key, inhalt, "text/csv")
    if lauf.fehlerbericht_key:
        await _objekt_loeschen(lauf.fehlerbericht_key)
    lauf.fehlerbericht_key = key


async def _objekt_loeschen(key: str) -> None:
    try:
        await storage_service.delete_object(key)
    except Exception:
        logger.warning("Importobjekt konnte nicht geloescht werden")


async def _quelle_entfernen(lauf: ImportLauf) -> None:
    if lauf.object_key:
        await _objekt_loeschen(lauf.object_key)
        lauf.object_key = None


async def fehlerbericht_fuer(
    session: AsyncSession, lauf: ImportLauf, user_id: UUID, arten: tuple[str, ...]
) -> bytes:
    if lauf.fehlerbericht_key and arten == ("fehler",):
        try:
            return await storage_service.download_bytes(lauf.fehlerbericht_key)
        except Exception:
            raise ImportFehler("Der Fehlerbericht ist nicht mehr verfügbar.", 410) from None
    if lauf.object_key is None or lauf.mapping is None or lauf.optionen is None:
        if lauf.fehlerbericht_key:
            raise ImportFehler("Dieser Bericht enthält nur Fehlerzeilen.", 404)
        raise ImportFehler("Für diesen Importlauf liegt kein Fehlerbericht vor.", 404)
    konfig = konfiguration_aus_lauf(lauf)
    tabelle = await lade_tabelle(lauf)
    ergebnisse = await _pruefen(session, lauf, tabelle, konfig, user_id)
    return await run_in_threadpool(fehlerbericht_bytes, tabelle, ergebnisse, arten)


def konfiguration_aus_lauf(lauf: ImportLauf) -> Konfiguration:
    optionen = lauf.optionen or {}
    return Konfiguration(
        mapping=dict(lauf.mapping or {}),
        modus=optionen.get("modus", "gueltige"),
        chargengroesse=optionen.get("chargengroesse", 200),
        dubletten_aktionen=dict(optionen.get("dubletten_aktionen", {})),
    )


# --- Verwerfen / Aufraeumen -----------------------------------------------------


async def verwerfen(session: AsyncSession, lauf: ImportLauf) -> None:
    if lauf.status not in ("analysiert", "geprueft", "abgebrochen"):
        raise ImportFehler("Nur nicht abgeschlossene Importläufe können verworfen werden.", 409)
    await _quelle_entfernen(lauf)
    lauf.status = "abgelaufen"
    await session.flush()


async def raeume_auf(jetzt: datetime | None = None) -> dict:
    """Entfernt Quelldateien nicht abgeschlossener Laeufe nach der Zwischenspeicher-Frist,
    uebrig gebliebene Quelldateien abgeschlossener Laeufe sowie Fehlerberichte nach ihrer
    Aufbewahrungsfrist. Die Laeufe selbst bleiben als Nachweis."""
    einstellungen = get_settings()
    jetzt = jetzt or datetime.now(UTC)
    quelle_grenze = jetzt - timedelta(hours=einstellungen.import_zwischenspeicher_stunden)
    bericht_grenze = jetzt - timedelta(days=einstellungen.import_fehlerbericht_tage)
    quellen = berichte = 0
    async with system_session() as session:
        alt = (
            await session.execute(
                select(ImportLauf).where(ImportLauf.object_key.is_not(None), ImportLauf.created_at < quelle_grenze)
            )
        ).scalars().all()
        for lauf in alt:
            await _objekt_loeschen(lauf.object_key)
            lauf.object_key = None
            if lauf.status in ("analysiert", "geprueft"):
                lauf.status = "abgelaufen"
            quellen += 1
        berichte_alt = (
            await session.execute(
                select(ImportLauf).where(
                    ImportLauf.fehlerbericht_key.is_not(None),
                    ImportLauf.updated_at < bericht_grenze,
                    ImportLauf.status.in_(("abgeschlossen", "rueckgaengig", "abgelaufen", "abgebrochen")),
                )
            )
        ).scalars().all()
        for lauf in berichte_alt:
            await _objekt_loeschen(lauf.fehlerbericht_key)
            lauf.fehlerbericht_key = None
            berichte += 1
    return {"quellen": quellen, "fehlerberichte": berichte}


# --- Vorlagen --------------------------------------------------------------------


def vorlage_bytes(definition: EntitaetDef) -> bytes:
    return csv_service.csv_bytes(list(definition.vorlage_kopf), [list(z) for z in definition.vorlage_zeilen])
