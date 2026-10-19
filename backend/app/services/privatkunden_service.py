"""Hinweise auf Rechnungen an Privatkunden (nicht gewerbliche Kunden, siehe
Kunde.ist_gewerblich): Aufbewahrungspflicht nach § 14 Abs. 4 Nr. 9 UStG und
der Ausweis der Arbeitskosten fuer die Steuerermaessigung nach § 35a EStG.

Dieselben Texte erscheinen im PDF (pdf_service.generate_rechnung_pdf) und als
Rechnungsvermerk in der E-Rechnung (rechnung_service), damit beide Darstellungen
uebereinstimmen. Abschaltbar je Mandant ueber firmendaten.privatkunden_hinweise.

Der Arbeitskostenausweis ist nur so verlaesslich wie die Zuordnung der Positionen:
Es zaehlen allein Positionen mit der Quelle zeit, fahrzeit oder fahrtkosten als
Arbeit und material als Material. Leistungsverzeichnis-Positionen (quelle
"leistung") und manuelle Positionen (quelle leer) koennen Lohn und Material
mischen -- enthaelt eine Rechnung eine solche Position, wird nichts geraten und
nur der Aufbewahrungshinweis ausgegeben."""
from dataclasses import dataclass
from decimal import Decimal

from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.rechnung import Rechnung, RechnungPosition
from app.services import steuer_service

ARBEITSKOSTEN_QUELLEN = ("zeit", "fahrzeit", "fahrtkosten")
_MATERIAL_QUELLE = "material"

# Hinweise gelten fuer Rechnungen ueber Leistungen; Gutschrift und Storno korrigieren
# nur eine bereits mit dem Hinweis versehene Rechnung.
_ARTEN_MIT_HINWEIS = ("rechnung", "abschlag", "schluss")
# Abschlaege und Schlussrechnungen (mit Abzugszeilen) lassen keine Zuordnung von
# Arbeit und Material zu.
_ARTEN_MIT_ARBEITSKOSTEN = ("rechnung",)

AUFBEWAHRUNGSHINWEIS = (
    "Hinweis nach § 14 Abs. 4 Nr. 9 UStG: Als Privatperson sind Sie verpflichtet, diese Rechnung "
    "zwei Jahre lang aufzubewahren. Die Frist beginnt mit dem Ablauf des Kalenderjahres, in dem die "
    "Rechnung ausgestellt wurde (§ 14b Abs. 1 Satz 5 UStG)."
)
UNBARE_ZAHLUNG_HINWEIS = (
    "Hinweis zu § 35a EStG: Die Steuerermäßigung setzt voraus, dass die Rechnung unbar bezahlt wird "
    "(Überweisung auf das angegebene Konto); Barzahlungen werden nicht anerkannt."
)


@dataclass(frozen=True)
class Arbeitskosten:
    netto: Decimal
    steuer: Decimal
    brutto: Decimal


@dataclass(frozen=True)
class Privatkundenhinweise:
    arbeitskosten: Arbeitskosten | None
    kleinunternehmer: bool
    unbare_zahlung: bool

    def texte(self) -> list[str]:
        """Absaetze in Ausgabereihenfolge (Arbeitskosten, Zahlungshinweis, Aufbewahrung)."""
        texte: list[str] = []
        if self.arbeitskosten is not None:
            kopf = "Davon Arbeitskosten inkl. Fahrt- und Maschinenkosten (§ 35a EStG): "
            if self.kleinunternehmer:
                texte.append(f"{kopf}{_eur(self.arbeitskosten.brutto)} (ohne Umsatzsteuer, § 19 UStG)")
            else:
                texte.append(
                    f"{kopf}Netto {_eur(self.arbeitskosten.netto)}, Umsatzsteuer {_eur(self.arbeitskosten.steuer)}, "
                    f"Brutto {_eur(self.arbeitskosten.brutto)}"
                )
            if self.unbare_zahlung:
                texte.append(UNBARE_ZAHLUNG_HINWEIS)
        texte.append(AUFBEWAHRUNGSHINWEIS)
        return texte


def _eur(betrag: Decimal) -> str:
    return f"{betrag:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " EUR"


def _arbeitskosten(rechnung: Rechnung, positionen: list[RechnungPosition]) -> Arbeitskosten | None:
    if rechnung.rechnungsart not in _ARTEN_MIT_ARBEITSKOSTEN or not positionen:
        return None
    if any(p.quelle not in (*ARBEITSKOSTEN_QUELLEN, _MATERIAL_QUELLE) for p in positionen):
        return None
    arbeit = [p for p in positionen if p.quelle in ARBEITSKOSTEN_QUELLEN]
    if not arbeit:
        return None
    gruppen = steuer_service.steuer_gruppen(rechnung, arbeit)
    netto, steuer = steuer_service.netto_summe(gruppen), steuer_service.steuer_summe(gruppen)
    return Arbeitskosten(netto=netto, steuer=steuer, brutto=netto + steuer)


def hinweise_fuer(
    mandant: Mandant, rechnung: Rechnung, kunde: Kunde, positionen: list[RechnungPosition]
) -> Privatkundenhinweise | None:
    """None, wenn der Beleg keine Hinweise tragen soll: Schalter aus, gewerblicher
    Kunde, Gutschrift oder Storno."""
    fd = mandant.firmendaten or {}
    if fd.get("privatkunden_hinweise") is False:
        return None
    if kunde.ist_gewerblich or rechnung.ist_storno or rechnung.rechnungsart not in _ARTEN_MIT_HINWEIS:
        return None
    arbeitskosten = _arbeitskosten(rechnung, positionen)
    return Privatkundenhinweise(
        arbeitskosten=arbeitskosten,
        kleinunternehmer=steuer_service.ist_kleinunternehmer(mandant),
        unbare_zahlung=arbeitskosten is not None and bool((fd.get("iban") or "").strip()),
    )
