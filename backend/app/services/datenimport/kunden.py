"""Kunden-Import: Zeilen pruefen (Probelauf) und schreiben.

Pruefung und Schreiben nutzen dieselben vorbereiteten Daten (ZeilenErgebnis.nutzlast), damit
der Probelauf exakt das zeigt, was der Import danach tut. Dubletten-Schluessel werden einmal
vorab aus dem Bestand geladen, nicht pro Zeile abgefragt."""
import re
import secrets
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.beleg_zaehler import BelegZaehler
from app.models.kunde import KUNDE_TYPEN, Kunde
from app.schemas.kunde import KundeCreate
from app.services import datev_service
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

_TYP_SYNONYME = {
    "privat": ("privat", "privatkunde", "privatperson", "b2c", "consumer", "endkunde", "p"),
    "gewerbe": ("gewerbe", "gewerbekunde", "firma", "firmenkunde", "unternehmen", "business", "b2b", "gewerblich", "g"),
    "oeffentlich": (
        "oeffentlich", "oeffentliche hand", "behoerde", "kommune", "oeffentlicher auftraggeber", "oeffentlicherauftraggeber",
        "stadt", "gemeinde", "verwaltung oeffentlich",
    ),
    "hausverwaltung": ("hausverwaltung", "hv", "weg", "wohnungsverwaltung", "immobilienverwaltung", "verwalter"),
}
_TYP_NACH_SYNONYM = {werte.schluessel(s): typ for typ, liste in _TYP_SYNONYME.items() for s in liste}
_KUNDENNUMMER_KREIS = re.compile(r"^K-(\d+)$", re.IGNORECASE)
_MAX_NUMMER, _MAX_NAME, _MAX_FELD = 50, 200, 255
_ARTEN = ("kundennummer", "ust_idnr", "name_plz", "email")
_BEZEICHNUNGEN = {
    "name": "Name", "typ": "Kundentyp", "leitweg_id": "Leitweg-ID", "debitorenkonto": "Debitorenkonto",
    "kundennummer": "Kundennummer", "ust_idnr": "USt-IdNr.",
}


def typ_aus_text(text: str) -> str | None:
    return _TYP_NACH_SYNONYM.get(werte.schluessel(text))


@dataclass
class _Bestand:
    id: UUID
    kundennummer: str
    name: str
    typ: str | None
    adresse: dict
    ust_idnr: str | None
    leitweg_id: str | None
    debitorenkonto: str | None
    notiz: str | None
    ansprechpartner: list
    aktiv: bool


@dataclass
class _Index:
    nummern: dict[str, _Bestand] = field(default_factory=dict)
    ust: dict[str, _Bestand] = field(default_factory=dict)
    name_plz: dict[tuple[str, str], _Bestand] = field(default_factory=dict)
    email: dict[str, _Bestand] = field(default_factory=dict)
    konten: set[str] = field(default_factory=set)
    nummern_exakt: set[str] = field(default_factory=set)
    # Schluessel der in dieser Datei neu angelegten Zeilen -> Zeilennummer.
    datei: dict[tuple[str, object], int] = field(default_factory=dict)
    datei_konten: dict[str, int] = field(default_factory=dict)
    datei_nummern: dict[str, int] = field(default_factory=dict)

    def eintragen(self, b: _Bestand) -> None:
        self.nummern_exakt.add(b.kundennummer)
        if not b.aktiv:
            return
        self.nummern.setdefault(b.kundennummer.strip().casefold(), b)
        if b.ust_idnr:
            self.ust.setdefault(werte.ust_idnr_normalisieren(b.ust_idnr)[0], b)
        plz = werte.plz_schluessel((b.adresse or {}).get("plz"))
        if plz and werte.schluessel(b.name):
            self.name_plz.setdefault((werte.schluessel(b.name), plz), b)
        for ap in b.ansprechpartner or []:
            mail = (ap.get("email") or "").strip().casefold()
            if mail:
                self.email.setdefault(mail, b)
        if b.debitorenkonto:
            self.konten.add(b.debitorenkonto)


class KundenVerarbeiter:
    entitaet = "kunden"

    async def pruefen(self, kontext: Kontext, tabelle: Tabelle, konfig: Konfiguration) -> list[ZeilenErgebnis]:
        index = await self._index_laden(kontext)
        sachkontenlaenge = datev_service.sachkontenlaenge_von(kontext.mandant)
        ergebnisse = []
        for nr, zeile in zeilen_iter(tabelle, konfig):
            if nr % 200 == 0:
                kontext.frist_pruefen()
            ergebnisse.append(self._zeile_pruefen(nr, zeile, konfig, index, sachkontenlaenge))
        return ergebnisse

    async def _index_laden(self, kontext: Kontext) -> _Index:
        index = _Index()
        spalten = (
            Kunde.id, Kunde.kundennummer, Kunde.name, Kunde.typ, Kunde.adresse, Kunde.ust_idnr, Kunde.leitweg_id,
            Kunde.debitorenkonto, Kunde.notiz, Kunde.ansprechpartner, Kunde.geloescht_am,
        )
        for zeile in (await kontext.session.execute(select(*spalten).where(Kunde.mandant_id == kontext.mandant_id))).all():
            bestand = _Bestand(
                id=zeile[0], kundennummer=zeile[1], name=zeile[2], typ=zeile[3], adresse=dict(zeile[4] or {}),
                ust_idnr=zeile[5], leitweg_id=zeile[6], debitorenkonto=zeile[7], notiz=zeile[8],
                ansprechpartner=list(zeile[9] or []), aktiv=zeile[10] is None,
            )
            index.eintragen(bestand)
            # Auch Kunden im Papierkorb halten ihr Debitorenkonto (siehe Kunde.debitorenkonto).
            if bestand.debitorenkonto:
                index.konten.add(bestand.debitorenkonto)
        return index

    def _zeile_pruefen(self, nr, zeile, konfig: Konfiguration, index: _Index, sachkontenlaenge: int) -> ZeilenErgebnis:
        erg = ZeilenErgebnis(nr=nr)
        warnungen: list[str] = []

        firma = zeile.text("name")
        vorname, nachname = zeile.text("vorname"), zeile.text("nachname")
        person = " ".join(t for t in (vorname, nachname) if t)
        name = firma or person
        kundennummer = zeile.text("kundennummer")
        erg.vorschau = vorschau_von({"kundennummer": kundennummer, "name": name})
        if not name:
            return erg.fehler("Name/Firma fehlt")
        if len(name) > _MAX_NAME:
            return erg.fehler(f"Name ist länger als {_MAX_NAME} Zeichen")
        if len(kundennummer) > _MAX_NUMMER:
            return erg.fehler(f"Kundennummer ist länger als {_MAX_NUMMER} Zeichen")

        typ = None
        if text := zeile.text("typ"):
            typ = typ_aus_text(text)
            if typ is None:
                warnungen.append(f"Kundentyp „{text}“ ist unbekannt – Typ bleibt leer (erlaubt: {', '.join(KUNDE_TYPEN)})")

        strasse = " ".join(t for t in (zeile.text("strasse"), zeile.text("hausnummer")) if t)
        plz, ort = zeile.text("plz"), zeile.text("ort")
        if any(len(t) > _MAX_FELD for t in (strasse, plz, ort)):
            return erg.fehler(f"Adressfelder sind länger als {_MAX_FELD} Zeichen")
        if plz.isdigit() and len(plz) == 4:
            warnungen.append("PLZ hat nur 4 Ziffern – möglicherweise fehlt eine führende Null")
        adresse = {k: v for k, v in (("strasse", strasse), ("plz", plz), ("ort", ort)) if v} or None
        erg.vorschau |= vorschau_von({"ort": ort})

        ust_text = zeile.text("ust_idnr")
        ust = None
        if ust_text:
            ust, ust_ok = werte.ust_idnr_normalisieren(ust_text)
            if not ust_ok:
                warnungen.append("USt-IdNr. hat kein gültiges Format – wird trotzdem übernommen")

        kontakt, kontakt_warnungen = self._kontakt(zeile, name, firma)
        warnungen += kontakt_warnungen

        konto = zeile.text("debitorenkonto") or None
        eingabe = {
            "kundennummer": kundennummer or None,
            "name": name,
            "typ": typ,
            "ansprechpartner": [kontakt] if kontakt else [],
            "adresse": adresse,
            "notiz": zeile.text("notiz", einzeilig=False) or None,
            "ust_idnr": ust,
            "leitweg_id": zeile.text("leitweg_id") or None,
            "debitorenkonto": konto,
        }
        try:
            geprueft = KundeCreate(**eingabe)
            if geprueft.debitorenkonto:
                datev_service.personenkonto_pruefen(geprueft.debitorenkonto, "debitor", sachkontenlaenge)
        except ValidationError as exc:
            return erg.fehler(pydantic_meldung(exc, _BEZEICHNUNGEN))
        except ValueError as exc:
            return erg.fehler(str(exc))

        eingabe["leitweg_id"] = geprueft.leitweg_id
        eingabe["debitorenkonto"] = geprueft.debitorenkonto
        eingabe["ansprechpartner"] = [a.model_dump(mode="json") for a in geprueft.ansprechpartner]
        schluessel_zeile = self._schluessel(eingabe)

        treffer = self._dublette_suchen(eingabe, schluessel_zeile, index)
        if treffer is None:
            if kundennummer and kundennummer in index.nummern_exakt:
                return erg.fehler("Kundennummer ist bereits durch einen Datensatz im Papierkorb belegt")
            if geprueft.debitorenkonto and (
                geprueft.debitorenkonto in index.konten or geprueft.debitorenkonto in index.datei_konten
            ):
                return erg.fehler("Debitorenkonto ist bereits einem anderen Kunden zugeordnet")
            self._merken(index, eingabe, schluessel_zeile, nr)
            erg.nutzlast = {"typ": "neu", "eingabe": eingabe}
            erg.meldungen += warnungen
            if warnungen:
                erg.status = "warnung"
            return erg

        art, bestand, in_datei = treffer
        erg.status, erg.dublette_art = "dublette", art
        erg.dublette_von = f"Zeile {in_datei}" if in_datei else f"{bestand.kundennummer} {bestand.name}"
        grund = {
            "kundennummer": "Kundennummer",
            "ust_idnr": "USt-IdNr.",
            "name_plz": "Name und PLZ",
            "email": "E-Mail-Adresse",
        }[art]
        ort_text = "in derselben Datei" if in_datei else "im Bestand"
        erg.meldungen.append(f"Dublette: gleiche {grund} wie {erg.dublette_von} ({ort_text})")
        if art == "kundennummer" and bestand and werte.schluessel(bestand.name) != werte.schluessel(name):
            erg.meldungen.append("Achtung: Der Name weicht vom vorhandenen Kunden ab")
        aktion = konfig.aktion_fuer(art)
        if aktion == "anlegen" and art != "kundennummer":
            if kundennummer and kundennummer in index.nummern_exakt:
                return erg.fehler("Kundennummer ist bereits vergeben")
            if geprueft.debitorenkonto and (
                geprueft.debitorenkonto in index.konten or geprueft.debitorenkonto in index.datei_konten
            ):
                return erg.fehler("Debitorenkonto ist bereits einem anderen Kunden zugeordnet")
            self._merken(index, eingabe, schluessel_zeile, nr)
            erg.aktion = "anlegen"
            erg.nutzlast = {"typ": "neu", "eingabe": eingabe}
            erg.meldungen.append("Wird trotzdem als neuer Kunde angelegt")
            erg.meldungen += warnungen
        elif aktion == "aktualisieren" and bestand is not None and in_datei is None:
            fuellung = self._fuellung(bestand, eingabe, index)
            if fuellung["felder"] or fuellung["adresse"] or fuellung["ansprechpartner"]:
                erg.aktion = "aktualisieren"
                erg.nutzlast = {"typ": "aktualisieren", "id": bestand.id, **fuellung}
                ergaenzt = list(fuellung["felder"]) + list(fuellung["adresse"]) + (
                    ["ansprechpartner"] if fuellung["ansprechpartner"] else []
                )
                erg.meldungen.append("Leere Felder werden ergänzt: " + ", ".join(ergaenzt))
            else:
                erg.aktion = "ueberspringen"
                erg.meldungen.append("Keine leeren Felder zu ergänzen – Zeile wird übersprungen")
        else:
            erg.aktion = "ueberspringen"
            if aktion == "aktualisieren" and in_datei:
                erg.meldungen.append("Zeile wird übersprungen (eine Dublette innerhalb der Datei lässt sich nicht aktualisieren)")
        return erg

    @staticmethod
    def _kontakt(zeile, name: str, firma: str) -> tuple[dict | None, list[str]]:
        warnungen: list[str] = []
        email = zeile.text("email")
        if email and not werte.email_gueltig(email):
            warnungen.append("E-Mail-Adresse ist ungültig – nicht übernommen")
            email = ""
        telefon = zeile.text("telefon") or zeile.text("mobil")
        if len(telefon) > 60:
            warnungen.append("Telefonnummer ist zu lang – nicht übernommen")
            telefon = ""
        ap_name = zeile.text("ansprechpartner")
        if not ap_name and firma:
            ap_name = " ".join(t for t in (zeile.text("vorname"), zeile.text("nachname")) if t)
        position = zeile.text("ansprechpartner_position")
        if not (email or telefon or ap_name or position):
            return None, warnungen
        kontakt = {"name": (ap_name or name)[:_MAX_NAME]}
        for schluessel_, wert in (("position", position[:_MAX_FELD]), ("telefon", telefon), ("email", email)):
            if wert:
                kontakt[schluessel_] = wert
        return kontakt, warnungen

    @staticmethod
    def _schluessel(eingabe: dict) -> dict[str, object]:
        schluessel: dict[str, object] = {}
        if eingabe["kundennummer"]:
            schluessel["kundennummer"] = eingabe["kundennummer"].strip().casefold()
        if eingabe["ust_idnr"]:
            schluessel["ust_idnr"] = werte.ust_idnr_normalisieren(eingabe["ust_idnr"])[0]
        plz = werte.plz_schluessel((eingabe["adresse"] or {}).get("plz"))
        if plz and werte.schluessel(eingabe["name"]):
            schluessel["name_plz"] = (werte.schluessel(eingabe["name"]), plz)
        mails = [a["email"].strip().casefold() for a in eingabe["ansprechpartner"] if a.get("email")]
        if mails:
            schluessel["email"] = mails
        return schluessel

    def _dublette_suchen(self, eingabe: dict, schluessel: dict, index: _Index):
        for art in _ARTEN:
            if art not in schluessel:
                continue
            wert = schluessel[art]
            werte_liste = wert if isinstance(wert, list) else [wert]
            for einzel in werte_liste:
                bestand = {
                    "kundennummer": index.nummern, "ust_idnr": index.ust, "name_plz": index.name_plz, "email": index.email,
                }[art].get(einzel)
                if bestand is not None:
                    return art, bestand, None
                zeile_in_datei = index.datei.get((art, einzel))
                if zeile_in_datei is not None:
                    return art, None, zeile_in_datei
        return None

    @staticmethod
    def _merken(index: _Index, eingabe: dict, schluessel: dict, nr: int) -> None:
        for art, wert in schluessel.items():
            for einzel in wert if isinstance(wert, list) else [wert]:
                index.datei.setdefault((art, einzel), nr)
        if eingabe["kundennummer"]:
            index.nummern_exakt.add(eingabe["kundennummer"])
            index.datei_nummern.setdefault(eingabe["kundennummer"], nr)
        if eingabe["debitorenkonto"]:
            index.datei_konten[eingabe["debitorenkonto"]] = nr

    @staticmethod
    def _fuellung(bestand: _Bestand, eingabe: dict, index: _Index) -> dict:
        """Welche leeren Felder des vorhandenen Kunden die Zeile ergaenzen wuerde. Der
        Bestands-Schnappschuss wird mitgefuehrt, damit eine zweite Zeile zum selben Kunden
        nichts doppelt ergaenzt."""
        felder: dict = {}
        for feld in ("typ", "ust_idnr", "leitweg_id", "notiz"):
            if not getattr(bestand, feld) and eingabe[feld]:
                felder[feld] = eingabe[feld]
                setattr(bestand, feld, eingabe[feld])
        konto = eingabe["debitorenkonto"]
        if not bestand.debitorenkonto and konto and konto not in index.konten and konto not in index.datei_konten:
            felder["debitorenkonto"] = konto
            bestand.debitorenkonto = konto
            index.konten.add(konto)
        adresse = {k: v for k, v in (eingabe["adresse"] or {}).items() if not (bestand.adresse or {}).get(k)}
        bestand.adresse = {**(bestand.adresse or {}), **adresse}
        kontakte = eingabe["ansprechpartner"] if not bestand.ansprechpartner else []
        if kontakte:
            bestand.ansprechpartner = list(kontakte)
        return {"felder": felder, "adresse": adresse, "ansprechpartner": kontakte}

    # --- Schreiben ---------------------------------------------------------

    async def vorbereiten_schreiben(self, kontext: Kontext, zeilen: list[ZeilenErgebnis]) -> None:
        """Vergibt Kundennummern fuer Zeilen ohne eigene und fuehrt den Nummernkreis nach."""
        neu = [z for z in zeilen if z.nutzlast and z.nutzlast["typ"] == "neu"]
        if not neu:
            return
        session = kontext.session
        explizit = [z.nutzlast["eingabe"]["kundennummer"] for z in neu if z.nutzlast["eingabe"]["kundennummer"]]
        im_kreis = [int(m.group(1)) for n in explizit if (m := _KUNDENNUMMER_KREIS.match(n))]
        if im_kreis:
            await _zaehler_mindestens(session, kontext.mandant_id, max(im_kreis) + 1)
        ohne = [z for z in neu if not z.nutzlast["eingabe"]["kundennummer"]]
        if not ohne:
            return
        belegt = set(explizit)
        belegt |= set((await session.execute(select(Kunde.kundennummer).where(Kunde.mandant_id == kontext.mandant_id))).scalars())
        offen = list(ohne)
        for _ in range(50):
            if not offen:
                break
            start = await _zaehler_reservieren(session, kontext.mandant_id, len(offen))
            rest = []
            for versatz, zeile in enumerate(offen):
                nummer = f"K-{start + versatz:05d}"
                if nummer in belegt:
                    rest.append(zeile)
                    continue
                belegt.add(nummer)
                zeile.nutzlast["eingabe"]["kundennummer"] = nummer
                zeile.vorschau["kundennummer"] = nummer
            offen = rest
        if offen:
            raise RuntimeError("Keine freien Kundennummern gefunden -- Nummernkreis pruefen.")

    async def schreiben(self, kontext: Kontext, zeilen: list[ZeilenErgebnis]) -> list[tuple[str, UUID, str, int]]:
        session = kontext.session
        eintraege: list[tuple[str, UUID, str, int]] = []
        neue: list[Kunde] = []
        for zeile in zeilen:
            nutzlast = zeile.nutzlast
            if not nutzlast or nutzlast["typ"] != "neu":
                continue
            e = nutzlast["eingabe"]
            kunde = Kunde(
                id=uuid4(),
                mandant_id=kontext.mandant_id,
                kundennummer=e["kundennummer"],
                name=e["name"],
                typ=e["typ"],
                ansprechpartner=[{**a, "id": a.get("id") or str(uuid4())} for a in e["ansprechpartner"]],
                adresse=e["adresse"],
                notiz=e["notiz"],
                ust_idnr=e["ust_idnr"],
                leitweg_id=e["leitweg_id"],
                debitorenkonto=e["debitorenkonto"],
                # Ein Link je Kunde, siehe create_kunde.
                portal_slug=secrets.token_urlsafe(12),
            )
            neue.append(kunde)
            eintraege.append(("kunde", kunde.id, "angelegt", zeile.nr))
        session.add_all(neue)

        updates = {z.nutzlast["id"]: z for z in zeilen if z.nutzlast and z.nutzlast["typ"] == "aktualisieren"}
        if updates:
            objekte = (await session.execute(select(Kunde).where(Kunde.id.in_(list(updates))))).scalars().all()
            for kunde in objekte:
                zeile = updates[kunde.id]
                plan = zeile.nutzlast
                for feld, wert in plan["felder"].items():
                    if not getattr(kunde, feld):
                        setattr(kunde, feld, wert)
                if plan["adresse"]:
                    kunde.adresse = {**plan["adresse"], **(kunde.adresse or {})}
                if plan["ansprechpartner"] and not kunde.ansprechpartner:
                    kunde.ansprechpartner = [{**a, "id": a.get("id") or str(uuid4())} for a in plan["ansprechpartner"]]
                eintraege.append(("kunde", kunde.id, "aktualisiert", zeile.nr))
        await session.flush()
        return eintraege


async def _zaehler_reservieren(session, mandant_id: UUID, anzahl: int) -> int:
    """Reserviert `anzahl` aufeinanderfolgende Laufnummern der Belegart "kunde" in einem
    atomaren Upsert (wie numbering_service._naechste_laufnummer, nur im Block) und gibt die
    erste zurueck."""
    stmt = (
        pg_insert(BelegZaehler)
        .values(mandant_id=mandant_id, belegart="kunde", naechste_nummer=1 + anzahl)
        .on_conflict_do_update(
            index_elements=[BelegZaehler.mandant_id, BelegZaehler.belegart],
            set_={"naechste_nummer": BelegZaehler.naechste_nummer + anzahl},
        )
        .returning(BelegZaehler.naechste_nummer)
    )
    return (await session.execute(stmt)).scalar_one() - anzahl


async def _zaehler_mindestens(session, mandant_id: UUID, minimum: int) -> None:
    """Hebt den Zaehler auf mindestens `minimum` an (nie ab): uebernommene Nummern im Format
    K-00123 duerfen von der automatischen Vergabe nicht erneut erzeugt werden."""
    stmt = (
        pg_insert(BelegZaehler)
        .values(mandant_id=mandant_id, belegart="kunde", naechste_nummer=minimum)
        .on_conflict_do_update(
            index_elements=[BelegZaehler.mandant_id, BelegZaehler.belegart],
            set_={"naechste_nummer": func.greatest(BelegZaehler.naechste_nummer, minimum)},
        )
    )
    await session.execute(stmt)

