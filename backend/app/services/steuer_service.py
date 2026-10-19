"""Einzige Wahrheit fuer die Steuer von Ausgangsrechnungen.

Netto/Steuer/Brutto werden nirgends persistiert, sondern ueberall aus den
Positionen berechnet -- in Python (steuer_gruppen) und, wo gefiltert/sortiert/
summiert wird, als SQL (netto_sql/steuer_sql/brutto_sql). Beide Wege bilden
dieselbe Regel ab, damit Liste, Detail, Summenzeile und Filter nie
auseinanderlaufen:

- Positionen werden nach (Steuerkategorie, Satz) gruppiert.
- Netto je Gruppe = Summe(menge * einzelpreis), auf Cent gerundet.
- Steuer je Gruppe = Gruppen-Netto * Satz / 100, auf Cent gerundet -- nie je
  Position (EN-16931-Konvention, sonst summieren sich Rundungsfehler).
- Gerundet wird kaufmaennisch (ROUND_HALF_UP, Postgres round() auf numeric
  rundet ebenso). Das Python-quantize() mit seinem Standard HALF_EVEN haette
  an exakten Halb-Cent-Faellen von der SQL-Seite abgewichen.
- Ohne Positionen (einfache Abschlussrechnung aus Phase 6) bildet
  betrag_netto mit mwst_satz des Belegs die einzige Gruppe.
- Der Steuergrund (Katalog STEUER_GRUENDE) fliesst bewusst NICHT in die
  Gruppierung der Berechnung ein: sonst wuerde die Rundung je Gruppe die
  Summen veraendern. Jede Gruppe sammelt nur die Hinweistexte ihrer
  Positionen (SteuerGruppe.hinweise) fuer PDF, E-Rechnung und API.
"""
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, NamedTuple

from sqlalchemy import func, select
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from app.models.rechnung import RECHNUNG_STEUER_KATEGORIEN, Rechnung, RechnungPosition

_CENT = Decimal("0.01")
_HUNDERT = Decimal("100")

# Reihenfolge der Gruppen in Anzeige und Auswertung.
_KATEGORIE_REIHENFOLGE = {kategorie: i for i, kategorie in enumerate(RECHNUNG_STEUER_KATEGORIEN)}

# Gating: welche Kategorien/Saetze per API angelegt werden duerfen. Z, E und
# AE sind nur mit passendem Steuergrund zulaessig (STEUER_GRUENDE); beim
# Kleinunternehmer (E/0) wird alles serverseitig erzwungen.
FREIGEGEBENE_STEUER_KATEGORIEN = ("S", "Z", "E", "AE")
ERLAUBTE_REGELSAETZE = (Decimal("19.00"), Decimal("7.00"))

# Steuergrund -> (Kategorie, Standardtext). Der Text erscheint auf der PDF und
# als Befreiungsgrund (BT-120) in der E-Rechnung. Bei sonstige_befreiung gibt
# es keinen Standardtext, er kommt aus rechnung_positionen.steuer_grund_text.
STEUER_GRUENDE: dict[str, tuple[str, str | None]] = {
    "pv_12_3": (
        "Z",
        "Nullsteuersatz nach § 12 Abs. 3 UStG (Lieferung und Installation von Photovoltaikanlagen)",
    ),
    "reverse_charge_13b": ("AE", "Steuerschuldnerschaft des Leistungsempfängers (§ 13b UStG)"),
    "kleinunternehmer_19": ("E", "Steuerbefreit nach § 19 UStG (Kleinunternehmerregelung)"),
    "sonstige_befreiung": ("E", None),
}
SONSTIGE_BEFREIUNG_TEXT_MIN = 3
SONSTIGE_BEFREIUNG_TEXT_MAX = 200


class SteuerFehler(ValueError):
    """Unzulaessige Steuerangabe an einer Position -- die Routen machen daraus
    ein 422 mit der (deutschen) Meldung."""


def runde_cent(wert: Decimal) -> Decimal:
    return Decimal(wert).quantize(_CENT, rounding=ROUND_HALF_UP)


def steuer_hinweis_text(position) -> str | None:
    """Hinweistext einer Position aus dem Katalog; None ohne (bekannten) Grund
    oder bei sonstige_befreiung ohne Text."""
    eintrag = STEUER_GRUENDE.get(position.steuer_grund or "")
    if eintrag is None:
        return None
    if eintrag[1] is not None:
        return eintrag[1]
    return (position.steuer_grund_text or "").strip() or None


@dataclass(frozen=True)
class SteuerGruppe:
    kategorie: str
    satz: Decimal
    netto: Decimal
    steuer: Decimal
    # Distinkte Hinweistexte der Positionen in Positionsreihenfolge; leer, wenn
    # keine Position einen Grund traegt.
    hinweise: tuple[str, ...] = ()
    # Distinkte Grund-Schluessel der Positionen (None = Position ohne Grund).
    gruende: tuple[str | None, ...] = ()

    @property
    def brutto(self) -> Decimal:
        return self.netto + self.steuer

    @property
    def hinweis(self) -> str | None:
        return "; ".join(self.hinweise) or None


def _satz(wert: Decimal) -> Decimal:
    return Decimal(wert).quantize(_CENT)


def kategorie_fuer_beleg_satz(satz: Decimal) -> str:
    """Kategorie einer Position, die nur den Satz des Belegs erbt. Satz 0 ist
    Kleinunternehmer-Bestand und wird wie bisher als Befreiung (E) gefuehrt."""
    return "E" if satz == 0 else "S"


def steuer_gruppen(rechnung: Rechnung, positionen: Iterable[RechnungPosition]) -> list[SteuerGruppe]:
    positionen = list(positionen)
    if not positionen:
        satz = _satz(rechnung.mwst_satz)
        netto = runde_cent(rechnung.betrag_netto)
        return [SteuerGruppe(kategorie_fuer_beleg_satz(satz), satz, netto, runde_cent(netto * satz / _HUNDERT))]

    summen: dict[tuple[str, Decimal], Decimal] = {}
    hinweise: dict[tuple[str, Decimal], list[str]] = {}
    gruende: dict[tuple[str, Decimal], list[str | None]] = {}
    for p in positionen:
        # Nicht gespeicherte Positionen (z. B. im Speicher gebaute Vorschau-
        # Positionen) haben noch keine Steuerfelder und erben vom Beleg.
        satz = _satz(rechnung.mwst_satz if p.steuer_satz is None else p.steuer_satz)
        schluessel = (p.steuer_kategorie or kategorie_fuer_beleg_satz(satz), satz)
        summen[schluessel] = summen.get(schluessel, Decimal("0")) + p.menge * p.einzelpreis
        hinweis = steuer_hinweis_text(p)
        if hinweis is not None and hinweis not in hinweise.setdefault(schluessel, []):
            hinweise[schluessel].append(hinweis)
        if p.steuer_grund not in gruende.setdefault(schluessel, []):
            gruende[schluessel].append(p.steuer_grund)
    gruppen = [
        SteuerGruppe(
            kategorie,
            satz,
            runde_cent(roh),
            runde_cent(runde_cent(roh) * satz / _HUNDERT),
            tuple(hinweise.get((kategorie, satz), ())),
            tuple(gruende[(kategorie, satz)]),
        )
        for (kategorie, satz), roh in summen.items()
    ]
    gruppen.sort(key=lambda g: (_KATEGORIE_REIHENFOLGE[g.kategorie], -g.satz))
    return gruppen


def netto_summe(gruppen: Iterable[SteuerGruppe]) -> Decimal:
    return sum((g.netto for g in gruppen), Decimal("0")).quantize(_CENT)


def steuer_summe(gruppen: Iterable[SteuerGruppe]) -> Decimal:
    return sum((g.steuer for g in gruppen), Decimal("0")).quantize(_CENT)


def brutto_summe(gruppen: Iterable[SteuerGruppe]) -> Decimal:
    return sum((g.brutto for g in gruppen), Decimal("0")).quantize(_CENT)


def ist_kleinunternehmer(mandant) -> bool:
    return bool((mandant.firmendaten or {}).get("ist_kleinunternehmer"))


def beleg_vorbelegung(beleg_mwst_satz: Decimal, *, kleinunternehmer: bool) -> tuple[str, Decimal]:
    """Steuerfelder einer Position ohne eigene Angabe: Kleinunternehmer immer
    E/0, sonst der Satz des Belegs (siehe kategorie_fuer_beleg_satz)."""
    satz = Decimal("0.00") if kleinunternehmer else _satz(beleg_mwst_satz)
    return kategorie_fuer_beleg_satz(satz), satz


class PositionSteuer(NamedTuple):
    kategorie: str
    satz: Decimal
    grund: str | None
    grund_text: str | None


def _pruefe_freigabe(kategorie: str, satz: Decimal) -> None:
    if kategorie not in RECHNUNG_STEUER_KATEGORIEN:
        raise SteuerFehler(f"Steuerkategorie {kategorie} ist unbekannt")
    if kategorie not in FREIGEGEBENE_STEUER_KATEGORIEN:
        raise SteuerFehler(f"Steuerkategorie {kategorie} ist noch nicht freigeschaltet")
    if kategorie != "S":
        if satz != 0:
            raise SteuerFehler(f"Bei Steuerkategorie {kategorie} muss der Steuersatz 0 sein")
        return
    if _satz(satz) not in ERLAUBTE_REGELSAETZE:
        erlaubt = " und ".join(f"{s:f}".rstrip("0").rstrip(".") + " %" for s in ERLAUBTE_REGELSAETZE)
        raise SteuerFehler(
            f"Steuersatz {satz:f} % ist bei Steuerkategorie S nicht erlaubt (erlaubt: {erlaubt})"
        )


def _normiere_grund(kategorie: str, grund: str | None, grund_text: str | None) -> tuple[str | None, str | None]:
    """Prueft den Steuergrund zur Kategorie (fuer Nicht-Kleinunternehmer; dort
    wird der Grund erzwungen) und liefert (Grund, Text) normalisiert."""
    text = (grund_text or "").strip() or None
    if grund != "sonstige_befreiung" and text is not None:
        raise SteuerFehler("steuer_grund_text ist nur bei sonstige_befreiung zulässig")
    if kategorie == "S":
        if grund is not None:
            raise SteuerFehler("Bei Steuerkategorie S ist kein Steuergrund vorgesehen")
        return None, None
    if kategorie == "Z":
        if grund != "pv_12_3":
            raise SteuerFehler("Für 0 % ist derzeit nur § 12 Abs. 3 UStG (Photovoltaik) vorgesehen")
        return grund, None
    if kategorie == "AE":
        if grund != "reverse_charge_13b":
            raise SteuerFehler("Bei Steuerkategorie AE (§ 13b UStG) muss der Steuergrund reverse_charge_13b sein")
        return grund, None
    if grund is None:
        raise SteuerFehler(
            "Steuerkategorie E (steuerfrei) braucht einen Steuergrund: sonstige_befreiung mit steuer_grund_text"
        )
    if grund == "kleinunternehmer_19":
        raise SteuerFehler("Der Steuergrund kleinunternehmer_19 gilt nur für Kleinunternehmer")
    if grund != "sonstige_befreiung":
        raise SteuerFehler(f"Der Steuergrund {grund} passt nicht zur Steuerkategorie E")
    if text is None or not (SONSTIGE_BEFREIUNG_TEXT_MIN <= len(text) <= SONSTIGE_BEFREIUNG_TEXT_MAX):
        raise SteuerFehler(
            f"Für sonstige Steuerbefreiungen ist ein Text von {SONSTIGE_BEFREIUNG_TEXT_MIN} bis "
            f"{SONSTIGE_BEFREIUNG_TEXT_MAX} Zeichen nötig (steuer_grund_text)"
        )
    return grund, text


_KLEINUNTERNEHMER_STEUER = PositionSteuer("E", Decimal("0.00"), "kleinunternehmer_19", None)


def loese_steuer_auf(
    *,
    kategorie: str | None,
    satz: Decimal | None,
    grund: str | None = None,
    grund_text: str | None = None,
    beleg_mwst_satz: Decimal,
    kleinunternehmer: bool,
) -> PositionSteuer:
    """Steuerfelder einer neu angelegten Position aus API-Angaben. Fehlt alles,
    gilt die Vorbelegung aus dem Beleg; ein daraus entstehender Satz
    ausserhalb der Regelsaetze wird wie eine explizite Angabe abgelehnt. Die
    geerbte Befreiung E/0 (Beleg mit Satz 0) ist Altverhalten, bleibt ohne
    Grund zulaessig und wird erst beim Versand geprueft. Nur mit Grund (ohne
    Kategorie) bestimmt der Katalog die Kategorie."""
    if kleinunternehmer:
        return _KLEINUNTERNEHMER_STEUER
    if kategorie is None and satz is None and grund is None and grund_text is None:
        kategorie_v, satz_v = beleg_vorbelegung(beleg_mwst_satz, kleinunternehmer=False)
        if kategorie_v != "E":
            _pruefe_freigabe(kategorie_v, satz_v)
        return PositionSteuer(kategorie_v, satz_v, None, None)
    if kategorie is None and grund in STEUER_GRUENDE:
        kategorie = STEUER_GRUENDE[grund][0]
    kategorie = kategorie or "S"
    if satz is None:
        satz = _satz(beleg_mwst_satz) if kategorie == "S" else Decimal("0.00")
    _pruefe_freigabe(kategorie, satz)
    grund, grund_text = _normiere_grund(kategorie, grund, grund_text)
    return PositionSteuer(kategorie, _satz(satz), grund, grund_text)


def aendere_steuer(
    *,
    aktuell_kategorie: str,
    aktuell_satz: Decimal,
    aktuell_grund: str | None = None,
    aktuell_grund_text: str | None = None,
    kategorie: str | None,
    satz: Decimal | None,
    grund: str | None = None,
    grund_text: str | None = None,
    kleinunternehmer: bool,
) -> PositionSteuer:
    """Steuerfelder einer bestehenden Position nach PATCH. Nicht angegebene
    Felder bleiben; wechselt nur die Kategorie auf eine ohne Satz, wird der
    Satz 0. Der Grund gehoert zur Kategorie und bleibt nur erhalten, solange
    sie sich nicht aendert -- ein Wechsel verlangt den neuen Grund."""
    if kleinunternehmer:
        return _KLEINUNTERNEHMER_STEUER
    if kategorie is None and grund in STEUER_GRUENDE:
        kategorie = STEUER_GRUENDE[grund][0]
    neue_kategorie = kategorie or aktuell_kategorie
    if satz is not None:
        neuer_satz = satz
    elif neue_kategorie != "S":
        neuer_satz = Decimal("0.00")
    else:
        neuer_satz = aktuell_satz
    _pruefe_freigabe(neue_kategorie, neuer_satz)
    if neue_kategorie != aktuell_kategorie:
        aktuell_grund = aktuell_grund_text = None
    neuer_grund = grund if grund is not None else aktuell_grund
    # Der Text gehoert zum Grund: bei neuem Grund gilt der alte Text nicht weiter.
    if grund_text is not None:
        neuer_text = grund_text
    else:
        neuer_text = aktuell_grund_text if neuer_grund == aktuell_grund else None
    neuer_grund, neuer_text = _normiere_grund(neue_kategorie, neuer_grund, neuer_text)
    return PositionSteuer(neue_kategorie, _satz(neuer_satz), neuer_grund, neuer_text)


# --- Voraussetzungen und Versandpruefung -------------------------------------


def _datum(tag: date) -> str:
    return tag.strftime("%d.%m.%Y")


MELDUNG_KUNDE_UST_IDNR_13B = "Beim Kunden fehlt die USt-IdNr. (Pflicht für Reverse Charge nach § 13b UStG)"
MELDUNG_MANDANT_UST_IDNR_13B = "Für Reverse Charge nach § 13b UStG fehlt die eigene USt-IdNr. in den Firmendaten"


def pruefe_13b_voraussetzungen(kunde, leistungsdatum: date | None, *, heute: date | None = None) -> list[str]:
    """Voraussetzungen fuer Reverse Charge (§ 13b UStG) beim Leistungsempfaenger:
    USt-IdNr. und eine zum Leistungszeitpunkt gueltige Bescheinigung USt 1 TG
    (§ 13b Abs. 2 Nr. 4 UStG). Ohne Leistungsdatum gilt der heutige Tag."""
    probleme: list[str] = []
    if not (kunde.ust_idnr or "").strip():
        probleme.append(MELDUNG_KUNDE_UST_IDNR_13B)
    bezugstag = leistungsdatum or heute or date.today()
    bezug = f"Leistungsdatum {_datum(leistungsdatum)}" if leistungsdatum else f"heute, {_datum(bezugstag)}"
    if kunde.ust_13b_nachweis_bis is None:
        probleme.append(
            "Beim Kunden fehlt das Ablaufdatum der Bescheinigung USt 1 TG (§ 13b Abs. 2 Nr. 4 UStG)"
        )
    elif kunde.ust_13b_nachweis_bis < bezugstag:
        probleme.append(
            f"Die Bescheinigung USt 1 TG des Kunden ist am {_datum(kunde.ust_13b_nachweis_bis)} abgelaufen ({bezug})"
        )
    return probleme


def pruefe_steuer_fuer_versand(mandant, rechnung, kunde, positionen: Iterable[RechnungPosition]) -> list[str]:
    """Steuerliche Pflichtangaben vor dem Versand einer Ausgangsrechnung. Der
    Kleinunternehmer ist ausgenommen: seine Steuerfelder werden beim Anlegen
    erzwungen. Geprueft wird hier (statt nur beim Anlegen), weil Entwuerfe aus
    Altbestand ohne Grund stammen und sich Kundendaten nachtraeglich aendern."""
    if ist_kleinunternehmer(mandant):
        return []
    positionen = list(positionen)
    probleme: list[str] = []
    if not positionen:
        if _satz(rechnung.mwst_satz) == 0:
            probleme.append(
                "Rechnung mit Steuersatz 0 % braucht Positionen mit Steuergrund "
                "(Steuerkategorie Z, E oder AE)"
            )
        return probleme

    for p in positionen:
        try:
            if p.steuer_kategorie == "S":
                continue
            _normiere_grund(p.steuer_kategorie, p.steuer_grund, p.steuer_grund_text)
        except SteuerFehler as exc:
            probleme.append(f"Position {p.position}: {exc}")

    if any(p.steuer_kategorie == "AE" for p in positionen):
        probleme.extend(pruefe_13b_voraussetzungen(kunde, rechnung.leistungsdatum))
        if not ((mandant.firmendaten or {}).get("ust_idnr") or "").strip():
            probleme.append(MELDUNG_MANDANT_UST_IDNR_13B)
    return probleme


# --- SQL-Gegenstuecke -------------------------------------------------------


def _gruppen_summe(je_gruppe, beleg=Rechnung) -> ColumnElement:
    """Summe von je_gruppe(netto, satz) ueber die Steuergruppen eines Belegs.
    Die innere Aggregation je (Kategorie, Satz) rundet das Gruppen-Netto
    (menge*einzelpreis vergroessert in Postgres die Skala auf 4); die aeussere
    Summe addiert die gerundeten Gruppenwerte -- exakt wie steuer_gruppen().
    beleg ist die Rechnung (Entity oder aliased()), auf die korreliert wird --
    Subqueries ueber ein anderes Rechnungs-Alias (Gutschriften, Bezugsrechnung)
    brauchen auch ein eigenes Positions-Alias, sonst verwechselt SQLAlchemy die
    Korrelation."""
    position = RechnungPosition if beleg is Rechnung else aliased(RechnungPosition)
    gruppen = (
        select(
            func.round(func.sum(position.menge * position.einzelpreis), 2).label("netto"),
            position.steuer_satz.label("satz"),
        )
        .where(position.rechnung_id == beleg.id)
        .group_by(position.steuer_kategorie, position.steuer_satz)
        .correlate(beleg)
        .subquery()
    )
    return select(func.sum(je_gruppe(gruppen.c.netto, gruppen.c.satz))).scalar_subquery()


def _steuer_von(netto, satz) -> ColumnElement:
    return func.round(netto * satz / _HUNDERT, 2)


def netto_sql(beleg=Rechnung) -> ColumnElement:
    """Fallback ohne Positionen: betrag_netto des Belegs (coalesce, weil die
    Gruppensumme nur ohne Positionen NULL ist)."""
    return func.coalesce(_gruppen_summe(lambda netto, satz: netto, beleg), func.round(beleg.betrag_netto, 2))


def steuer_sql(beleg=Rechnung) -> ColumnElement:
    return func.coalesce(
        _gruppen_summe(_steuer_von, beleg),
        _steuer_von(func.round(beleg.betrag_netto, 2), beleg.mwst_satz),
    )


def brutto_sql(beleg=Rechnung) -> ColumnElement:
    return func.coalesce(
        _gruppen_summe(lambda netto, satz: netto + _steuer_von(netto, satz), beleg),
        func.round(beleg.betrag_netto, 2) + _steuer_von(func.round(beleg.betrag_netto, 2), beleg.mwst_satz),
    )
