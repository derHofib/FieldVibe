"""Anlagen-Import (mit Standort und Pruefdaten).

Jede Zeile ist eine Anlage (oder, ohne Anlagenbezeichnung, nur ein Standort). Der Kunde wird
ueber Kundennummer oder eindeutigen Kundennamen zugeordnet. Pruefintervall und letzte Pruefung
ergeben einen Pruefzyklus nach demselben Muster wie POST /api/pruefzyklen."""
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select

from app.models.anlage import Anlage
from app.models.kunde import Kunde
from app.models.pruefzyklus import Pruefzyklus
from app.models.standort import Standort
from app.schemas.anlage import AnlageCreate
from app.schemas.standort import StandortCreate
from app.services.date_utils import add_intervall
from app.services.datenimport import werte
from app.services.datenimport.basis import (
    Konfiguration,
    Kontext,
    ZeilenErgebnis,
    pydantic_meldung,
    vorschau_von,
    zeilen_iter,
)
from app.services.datenimport.parser import Tabelle

_STANDARD_PRUEFUNG = "Regelprüfung"
_MAX_INTERVALL_MONATE = 1200
_MAX_FELD = 255
_BEZEICHNUNGEN = {"bezeichnung": "Anlagenbezeichnung", "anschaffungsdatum": "Anschaffungsdatum"}
_FUELL_FELDER = ("anlagentyp", "hersteller", "modell", "seriennummer", "anschaffungsdatum", "notiz")


@dataclass
class _StandortInfo:
    id: UUID
    adresse: dict
    # Zeilennummer, falls der Standort erst in dieser Datei angelegt wird.
    zeile: int | None = None


@dataclass
class _AnlagenBestand:
    id: UUID
    kunde_id: UUID
    standort_id: UUID | None
    bezeichnung: str
    felder: dict
    adresse: dict


@dataclass
class _Index:
    kunden_nummer: dict[str, UUID] = field(default_factory=dict)
    kunden_name: dict[str, list[UUID]] = field(default_factory=dict)
    standorte: dict[tuple[UUID, str], _StandortInfo] = field(default_factory=dict)
    seriennummern: dict[tuple[UUID, str], _AnlagenBestand] = field(default_factory=dict)
    bezeichnungen: dict[tuple[UUID, str, UUID | None], _AnlagenBestand] = field(default_factory=dict)
    mit_pruefzyklus: set[UUID] = field(default_factory=set)
    datei_seriennummern: dict[tuple[UUID, str], int] = field(default_factory=dict)
    datei_bezeichnungen: dict[tuple[UUID, str, UUID | None], int] = field(default_factory=dict)


class AnlagenVerarbeiter:
    entitaet = "anlagen"

    async def pruefen(self, kontext: Kontext, tabelle: Tabelle, konfig: Konfiguration) -> list[ZeilenErgebnis]:
        pruefzyklen_aktiv = "pruefzyklen" not in set(kontext.mandant.deaktivierte_module)
        index = await self._index_laden(kontext, pruefzyklen_aktiv)
        ergebnisse = []
        for nr, zeile in zeilen_iter(tabelle, konfig):
            if nr % 200 == 0:
                kontext.frist_pruefen()
            ergebnisse.append(self._zeile_pruefen(nr, zeile, konfig, index, pruefzyklen_aktiv))
        return ergebnisse

    async def _index_laden(self, kontext: Kontext, pruefzyklen_aktiv: bool) -> _Index:
        session, mandant_id = kontext.session, kontext.mandant_id
        index = _Index()
        kunden = await session.execute(
            select(Kunde.id, Kunde.kundennummer, Kunde.name).where(Kunde.mandant_id == mandant_id, Kunde.geloescht_am.is_(None))
        )
        for kid, nummer, name in kunden.all():
            index.kunden_nummer.setdefault(nummer.strip().casefold(), kid)
            index.kunden_name.setdefault(werte.schluessel(name), []).append(kid)
        standorte = await session.execute(
            select(Standort.id, Standort.kunde_id, Standort.bezeichnung, Standort.adresse).where(
                Standort.mandant_id == mandant_id, Standort.geloescht_am.is_(None)
            )
        )
        for sid, kid, bezeichnung, adresse in standorte.all():
            index.standorte.setdefault((kid, werte.schluessel(bezeichnung)), _StandortInfo(sid, dict(adresse or {})))
        spalten = (
            Anlage.id, Anlage.kunde_id, Anlage.standort_id, Anlage.bezeichnung, Anlage.seriennummer, Anlage.anlagentyp,
            Anlage.hersteller, Anlage.modell, Anlage.anschaffungsdatum, Anlage.notiz, Anlage.adresse,
        )
        anlagen = await session.execute(
            select(*spalten).where(
                Anlage.mandant_id == mandant_id, Anlage.objekttyp == "kundenanlage", Anlage.geloescht_am.is_(None)
            )
        )
        for z in anlagen.all():
            bestand = _AnlagenBestand(
                id=z[0], kunde_id=z[1], standort_id=z[2], bezeichnung=z[3],
                felder={"seriennummer": z[4], "anlagentyp": z[5], "hersteller": z[6], "modell": z[7],
                        "anschaffungsdatum": z[8], "notiz": z[9]},
                adresse=dict(z[10] or {}),
            )
            if z[4] and werte.schluessel(z[4]):
                index.seriennummern.setdefault((z[1], werte.schluessel(z[4])), bestand)
            index.bezeichnungen.setdefault((z[1], werte.schluessel(z[3]), z[2]), bestand)
        if pruefzyklen_aktiv:
            index.mit_pruefzyklus = set(
                (await session.execute(
                    select(Pruefzyklus.anlage_id).where(Pruefzyklus.mandant_id == mandant_id, Pruefzyklus.geloescht_am.is_(None))
                )).scalars()
            )
        return index

    # --- Zeile ---------------------------------------------------------------

    def _kunde_finden(self, zeile, index: _Index) -> UUID | str:
        """Kunden-ID oder (str) die Fehlermeldung."""
        nummer, name = zeile.text("kundennummer"), zeile.text("kundenname")
        if nummer:
            kid = index.kunden_nummer.get(nummer.casefold())
            return kid if kid is not None else "Kunde mit dieser Kundennummer nicht gefunden (unbekannt)"
        if name:
            treffer = index.kunden_name.get(werte.schluessel(name), [])
            if not treffer:
                return "Kunde mit diesem Namen nicht gefunden (unbekannt)"
            if len(treffer) > 1:
                return f"Kundenname ist mehrdeutig ({len(treffer)} Kunden gleichen Namens) – bitte die Kundennummer angeben"
            return treffer[0]
        return "Kunde fehlt (Kundennummer oder Kundenname angeben)"

    def _zeile_pruefen(self, nr, zeile, konfig: Konfiguration, index: _Index, pruefzyklen_aktiv: bool) -> ZeilenErgebnis:
        erg = ZeilenErgebnis(nr=nr)
        warnungen: list[str] = []
        a_bez, st_bez = zeile.text("bezeichnung"), zeile.text("standort_bezeichnung")
        erg.vorschau = vorschau_von(
            {"kunde": zeile.text("kundennummer") or zeile.text("kundenname"), "standort": st_bez, "anlage": a_bez}
        )
        if not a_bez and not st_bez:
            return erg.fehler("Weder Anlagenbezeichnung noch Standort angegeben")
        if len(a_bez) > _MAX_FELD or len(st_bez) > _MAX_FELD:
            return erg.fehler(f"Bezeichnungen sind länger als {_MAX_FELD} Zeichen")

        kunde = self._kunde_finden(zeile, index)
        if isinstance(kunde, str):
            return erg.fehler(kunde)

        strasse = " ".join(t for t in (zeile.text("strasse"), zeile.text("hausnummer")) if t)
        plz, ort = zeile.text("plz"), zeile.text("ort")
        adresse = {k: v for k, v in (("strasse", strasse), ("plz", plz), ("ort", ort)) if v}
        if plz.isdigit() and len(plz) == 4:
            warnungen.append("PLZ hat nur 4 Ziffern – möglicherweise fehlt eine führende Null")

        # Prüfdaten zuerst: ein Fehler dort verhindert die ganze Zeile (Fristen sind sicherheitsrelevant).
        pruefung, meldung_pruefung, w = self._pruefdaten(zeile, pruefzyklen_aktiv)
        if meldung_pruefung:
            return erg.fehler(meldung_pruefung)
        warnungen += w

        standort_plan = None
        standort_id = None
        vorhanden = None
        if st_bez:
            st_key = (kunde, werte.schluessel(st_bez))
            vorhanden = index.standorte.get(st_key)
            if vorhanden is not None:
                standort_id = vorhanden.id
                standort_plan = {"id": vorhanden.id, "neu": False, "adresse": vorhanden.adresse}
            else:
                try:
                    StandortCreate(kunde_id=kunde, bezeichnung=st_bez, adresse=adresse)
                except ValidationError as exc:
                    return erg.fehler(pydantic_meldung(exc))
                standort_id = uuid4()
                standort_plan = {"id": standort_id, "neu": True, "kunde_id": kunde, "bezeichnung": st_bez, "adresse": adresse}

        if not a_bez:
            return self._standort_zeile(erg, konfig, index, kunde, st_bez, standort_plan, vorhanden, adresse, nr, warnungen)

        anlage, meldung = self._anlage_felder(zeile, kunde, a_bez, adresse, standort_plan, warnungen)
        if meldung:
            return erg.fehler(meldung)

        serial_key = werte.schluessel(anlage["seriennummer"]) if anlage["seriennummer"] else ""
        bez_key = (kunde, werte.schluessel(a_bez), standort_id)
        treffer = None
        if serial_key:
            if (b := index.seriennummern.get((kunde, serial_key))) is not None:
                treffer = ("seriennummer_kunde", b, None)
            elif (n := index.datei_seriennummern.get((kunde, serial_key))) is not None:
                treffer = ("seriennummer_kunde", None, n)
        if treffer is None:
            if (b := index.bezeichnungen.get(bez_key)) is not None:
                treffer = ("bezeichnung_standort", b, None)
            elif (n := index.datei_bezeichnungen.get(bez_key)) is not None:
                treffer = ("bezeichnung_standort", None, n)

        nutzlast = {
            "typ": "anlage_neu", "kunde_id": kunde, "standort": standort_plan, "anlage": anlage, "pruefzyklus": pruefung,
        }
        if treffer is None:
            self._merken(index, kunde, serial_key, bez_key, nr, standort_plan)
            erg.nutzlast = nutzlast
            erg.meldungen += warnungen
            if warnungen:
                erg.status = "warnung"
            return erg

        art, bestand, in_datei = treffer
        erg.status, erg.dublette_art = "dublette", art
        erg.dublette_von = f"Zeile {in_datei}" if in_datei else bestand.bezeichnung
        grund = "Seriennummer beim selben Kunden" if art == "seriennummer_kunde" else "Bezeichnung am selben Standort"
        erg.meldungen.append(
            f"Dublette: gleiche {grund} wie {erg.dublette_von} ({'in derselben Datei' if in_datei else 'im Bestand'})"
        )
        aktion = konfig.aktion_fuer(art)
        if aktion == "anlegen":
            self._merken(index, kunde, serial_key, bez_key, nr, standort_plan)
            erg.nutzlast = nutzlast
            erg.meldungen.append("Wird trotzdem als neue Anlage angelegt")
            erg.meldungen += warnungen
        elif aktion == "aktualisieren" and bestand is not None:
            plan = self._fuellung(bestand, anlage, adresse, standort_plan, pruefung, index)
            if plan["felder"] or plan["adresse"] or plan["standort"] or plan["pruefzyklus"]:
                erg.aktion = "aktualisieren"
                erg.nutzlast = {"typ": "anlage_update", "id": bestand.id, "kunde_id": kunde, **plan}
                ergaenzt = list(plan["felder"]) + (["adresse"] if plan["adresse"] else []) + (
                    ["standort"] if plan["standort"] else []) + (["prüfzyklus"] if plan["pruefzyklus"] else [])
                erg.meldungen.append("Leere Felder werden ergänzt: " + ", ".join(ergaenzt))
            else:
                erg.aktion = "ueberspringen"
                erg.meldungen.append("Keine leeren Felder zu ergänzen – Zeile wird übersprungen")
        else:
            erg.aktion = "ueberspringen"
            if aktion == "aktualisieren":
                erg.meldungen.append("Zeile wird übersprungen (eine Dublette innerhalb der Datei lässt sich nicht aktualisieren)")
        return erg

    def _standort_zeile(self, erg, konfig, index, kunde, st_bez, plan, vorhanden, adresse, nr, warnungen):
        """Zeile ohne Anlagenbezeichnung: legt nur den Standort an."""
        if vorhanden is not None:
            in_datei = vorhanden.zeile is not None
            erg.status, erg.dublette_art = "dublette", "standort"
            erg.dublette_von = f"Zeile {vorhanden.zeile}" if in_datei else st_bez
            erg.meldungen.append(
                "Dublette: Standort existiert bereits " + ("in derselben Datei" if in_datei else "im Bestand")
            )
            aktion = konfig.aktion_fuer("standort")
            if aktion == "anlegen":
                neu = {"id": uuid4(), "neu": True, "kunde_id": kunde, "bezeichnung": st_bez, "adresse": adresse}
                erg.nutzlast = {"typ": "standort_neu", "kunde_id": kunde, "standort": neu}
                erg.meldungen.append("Wird trotzdem als neuer Standort angelegt")
            elif aktion == "aktualisieren" and not in_datei and adresse and not vorhanden.adresse:
                erg.aktion = "aktualisieren"
                erg.nutzlast = {"typ": "standort_update", "id": vorhanden.id, "adresse": adresse}
                vorhanden.adresse = dict(adresse)
                erg.meldungen.append("Leere Felder werden ergänzt: adresse")
            else:
                erg.aktion = "ueberspringen"
            return erg
        index.standorte[(kunde, werte.schluessel(st_bez))] = _StandortInfo(plan["id"], dict(adresse), zeile=nr)
        erg.nutzlast = {"typ": "standort_neu", "kunde_id": kunde, "standort": plan}
        erg.meldungen += warnungen
        if warnungen:
            erg.status = "warnung"
        return erg

    @staticmethod
    def _merken(index: _Index, kunde, serial_key, bez_key, nr, standort_plan) -> None:
        if serial_key:
            index.datei_seriennummern.setdefault((kunde, serial_key), nr)
        index.datei_bezeichnungen.setdefault(bez_key, nr)
        if standort_plan and standort_plan["neu"]:
            index.standorte.setdefault(
                (kunde, werte.schluessel(standort_plan["bezeichnung"])),
                _StandortInfo(standort_plan["id"], dict(standort_plan["adresse"]), zeile=nr),
            )

    @staticmethod
    def _pruefdaten(zeile, aktiv: bool) -> tuple[dict | None, str | None, list[str]]:
        """(Pruefzyklus-Plan | None, Fehlermeldung | None, Warnungen)."""
        warnungen: list[str] = []
        roh_intervall = re.sub(r"(?i)\s*(monate?|mon\.?)\s*$", "", zeile.roh("pruefintervall_monate").strip())
        try:
            intervall = werte.parse_ganzzahl(roh_intervall)
        except ValueError:
            return None, "Prüfintervall muss eine ganze Zahl in Monaten sein", warnungen
        try:
            letzte = werte.parse_datum(zeile.roh("letzte_pruefung"))
        except ValueError:
            return None, "Letzte Prüfung ist kein gültiges Datum (erwartet TT.MM.JJJJ oder JJJJ-MM-TT)", warnungen
        try:
            naechste = werte.parse_datum(zeile.roh("naechste_pruefung"))
        except ValueError:
            return None, "Nächste Prüfung ist kein gültiges Datum (erwartet TT.MM.JJJJ oder JJJJ-MM-TT)", warnungen
        if intervall is None and letzte is None and naechste is None:
            return None, None, warnungen
        if not aktiv:
            warnungen.append("Das Modul Prüfzyklen ist nicht aktiv – Prüfdaten werden nicht übernommen")
            return None, None, warnungen
        if intervall is None:
            warnungen.append("Prüfdaten ohne Prüfintervall werden nicht übernommen (kein Prüfzyklus angelegt)")
            return None, None, warnungen
        if not 1 <= intervall <= _MAX_INTERVALL_MONATE:
            return None, f"Prüfintervall muss zwischen 1 und {_MAX_INTERVALL_MONATE} Monaten liegen", warnungen
        if letzte is not None:
            basis = datetime.combine(letzte, time.min, tzinfo=UTC)
        else:
            basis = datetime.now(UTC)
            warnungen.append("Ohne letzte Prüfung wird die nächste Prüfung ab heute berechnet")
        if naechste is not None:
            faellig = datetime.combine(naechste, time.min, tzinfo=UTC)
        else:
            faellig = add_intervall(basis, "monat", intervall)
        bezeichnung = zeile.text("pruefung_bezeichnung")[:_MAX_FELD] or _STANDARD_PRUEFUNG
        return {
            "bezeichnung": bezeichnung, "intervall_wert": intervall, "letzte_pruefung_am": basis if letzte else None,
            "naechste_pruefung_am": faellig,
        }, None, warnungen

    def _anlage_felder(self, zeile, kunde, a_bez, adresse, standort_plan, warnungen):
        notiz = zeile.text("notiz", einzeilig=False)
        baujahr_text = zeile.roh("baujahr").strip()
        if baujahr_text:
            try:
                jahr = werte.parse_jahr(zeile.roh("baujahr"))
                notiz = f"Baujahr: {jahr}" + (f"\n{notiz}" if notiz else "")
            except ValueError:
                warnungen.append("Baujahr ist ungültig – nicht übernommen")
        anschaffung = None
        if zeile.roh("anschaffungsdatum").strip():
            try:
                anschaffung = werte.parse_datum(zeile.roh("anschaffungsdatum"))
            except ValueError:
                warnungen.append("Anschaffungsdatum ist ungültig – nicht übernommen")
        # Ohne eigene Adresse gilt die des Standorts.
        eigene_adresse = adresse or (standort_plan.get("adresse") if standort_plan else None) or {}
        eingabe = {
            "kunde_id": kunde, "standort_id": standort_plan["id"] if standort_plan else None, "bezeichnung": a_bez,
            "adresse": dict(eigene_adresse), "anlagentyp": zeile.text("anlagentyp")[:_MAX_FELD] or None,
            "hersteller": zeile.text("hersteller")[:_MAX_FELD] or None, "modell": zeile.text("modell")[:_MAX_FELD] or None,
            "seriennummer": zeile.text("seriennummer")[:_MAX_FELD] or None, "anschaffungsdatum": anschaffung,
            "notiz": notiz or None,
        }
        try:
            AnlageCreate(**eingabe)
        except ValidationError as exc:
            return None, pydantic_meldung(exc, _BEZEICHNUNGEN)
        return {k: v for k, v in eingabe.items() if k not in ("kunde_id", "standort_id")}, None

    @staticmethod
    def _fuellung(bestand: _AnlagenBestand, anlage: dict, adresse: dict, standort_plan, pruefung, index: _Index) -> dict:
        felder = {}
        for feld in _FUELL_FELDER:
            if not bestand.felder.get(feld) and anlage.get(feld):
                felder[feld] = anlage[feld]
                bestand.felder[feld] = anlage[feld]
        neue_adresse = {}
        if not bestand.adresse and anlage["adresse"]:
            neue_adresse = dict(anlage["adresse"])
            bestand.adresse = neue_adresse
        standort = None
        if bestand.standort_id is None and standort_plan is not None:
            standort = standort_plan
            bestand.standort_id = standort_plan["id"]
        pz = None
        if pruefung is not None and bestand.id not in index.mit_pruefzyklus:
            pz = pruefung
            index.mit_pruefzyklus.add(bestand.id)
        return {"felder": felder, "adresse": neue_adresse, "standort": standort, "pruefzyklus": pz}

    # --- Schreiben ---------------------------------------------------------------

    async def vorbereiten_schreiben(self, kontext: Kontext, zeilen: list[ZeilenErgebnis]) -> None:
        kontext.extra["standorte_ok"] = set()

    async def schreiben(self, kontext: Kontext, zeilen: list[ZeilenErgebnis]) -> list[tuple[str, UUID, str, int]]:
        session, mandant_id = kontext.session, kontext.mandant_id
        bereits: set = kontext.extra["standorte_ok"]
        eintraege: list[tuple[str, UUID, str, int]] = []
        neue_standorte: dict[UUID, Standort] = {}

        def standort_anlegen(plan: dict, nr: int) -> None:
            if not plan or not plan["neu"] or plan["id"] in bereits or plan["id"] in neue_standorte:
                return
            neue_standorte[plan["id"]] = Standort(
                id=plan["id"], mandant_id=mandant_id, kunde_id=plan["kunde_id"], bezeichnung=plan["bezeichnung"],
                adresse=plan["adresse"],
            )
            eintraege.append(("standort", plan["id"], "angelegt", nr))

        for z in zeilen:
            n = z.nutzlast
            if not n:
                continue
            if n["typ"] in ("anlage_neu", "standort_neu"):
                standort_anlegen(n["standort"], z.nr)
            elif n["typ"] == "anlage_update" and n["standort"]:
                standort_anlegen(n["standort"], z.nr)
        session.add_all(neue_standorte.values())
        await session.flush()

        neue_anlagen: list[tuple[ZeilenErgebnis, Anlage]] = []
        for z in zeilen:
            n = z.nutzlast
            if not n or n["typ"] != "anlage_neu":
                continue
            anlage = Anlage(id=uuid4(), mandant_id=mandant_id, kunde_id=n["kunde_id"],
                            standort_id=n["standort"]["id"] if n["standort"] else None, objekttyp="kundenanlage", **n["anlage"])
            neue_anlagen.append((z, anlage))
            eintraege.append(("anlage", anlage.id, "angelegt", z.nr))
        session.add_all(a for _, a in neue_anlagen)

        updates = {z.nutzlast["id"]: z for z in zeilen if z.nutzlast and z.nutzlast["typ"] == "anlage_update"}
        if updates:
            for anlage in (await session.execute(select(Anlage).where(Anlage.id.in_(list(updates))))).scalars():
                z = updates[anlage.id]
                plan = z.nutzlast
                for feld, wert in plan["felder"].items():
                    if not getattr(anlage, feld):
                        setattr(anlage, feld, wert)
                if plan["adresse"] and not anlage.adresse:
                    anlage.adresse = plan["adresse"]
                if plan["standort"] and anlage.standort_id is None:
                    anlage.standort_id = plan["standort"]["id"]
                eintraege.append(("anlage", anlage.id, "aktualisiert", z.nr))
        st_updates = {z.nutzlast["id"]: z for z in zeilen if z.nutzlast and z.nutzlast["typ"] == "standort_update"}
        if st_updates:
            for standort in (await session.execute(select(Standort).where(Standort.id.in_(list(st_updates))))).scalars():
                if not standort.adresse:
                    standort.adresse = st_updates[standort.id].nutzlast["adresse"]
                eintraege.append(("standort", standort.id, "aktualisiert", st_updates[standort.id].nr))
        await session.flush()

        pruefzyklen = []
        ziele = [(z, a.id) for z, a in neue_anlagen] + [(z, anlage_id) for anlage_id, z in updates.items()]
        for z, anlage_id in ziele:
            if z.nutzlast["pruefzyklus"]:
                pz = Pruefzyklus(id=uuid4(), mandant_id=mandant_id, anlage_id=anlage_id, **z.nutzlast["pruefzyklus"])
                pruefzyklen.append(pz)
                eintraege.append(("pruefzyklus", pz.id, "angelegt", z.nr))
        session.add_all(pruefzyklen)
        await session.flush()
        bereits |= set(neue_standorte)
        return eintraege
