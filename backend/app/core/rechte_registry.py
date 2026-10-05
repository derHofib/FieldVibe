"""Registry der Rechte-Bereiche, -Aktionen und -Scopes (einzige Quelle der Wahrheit).

Ersetzt die frueher dreifach hart verdrahteten Listen (DB-Check-Constraints,
Python-Tupel, Frontend-Matrix): die DB validiert bereich/aktion nicht mehr,
Eingaben werden gegen diese Registry geprueft (siehe docs/konzepte/ORGANIGRAMM.md).
Bewusst ohne Imports aus app.models, damit models/account_typ.py sie nutzen kann.
"""
from dataclasses import dataclass

# Reihenfolge = Rang: ein hoeherer Scope umfasst alle niedrigeren.
SCOPES: tuple[str, ...] = ("eigene", "team", "teilbaum", "bereich", "mandant")
SCOPE_RANG: dict[str, int] = {scope: rang for rang, scope in enumerate(SCOPES)}

BASIS_AKTIONEN: tuple[str, ...] = ("sehen", "erstellen", "bearbeiten", "loeschen", "exportieren")

# team/teilbaum/bereich gibt es nur bei Daten mit zustaendiger Person
# (Vorgaenge, Termine/Zeiten, Projektaufgaben, Kunden); sonst nur "mandant".
_VOLLE_KETTE = SCOPES
_NUR_MANDANT: tuple[str, ...] = ("mandant",)


@dataclass(frozen=True)
class RechteBereichDef:
    key: str
    label: str
    aktionen: tuple[str, ...]
    scopes: tuple[str, ...]
    # Bezug zu MANDANT_MODULE (models/mandant.py): ist das Modul deaktiviert,
    # hat der Bereich keine Wirkung.
    modul: str | None = None


def _bereich(
    key: str,
    label: str,
    *,
    zusatz: tuple[str, ...] = (),
    scopes: tuple[str, ...] = _NUR_MANDANT,
    modul: str | None = None,
) -> RechteBereichDef:
    return RechteBereichDef(key=key, label=label, aktionen=BASIS_AKTIONEN + zusatz, scopes=scopes, modul=modul)


_BEREICHE: tuple[RechteBereichDef, ...] = (
    _bereich("vorgaenge", "Aufträge", scopes=_VOLLE_KETTE),
    _bereich("kunden", "Kunden & Anlagen", scopes=_VOLLE_KETTE, modul="kundenverwaltung"),
    _bereich("material", "Material", modul="material"),
    _bereich("dispo", "Dispo/Termine", scopes=_VOLLE_KETTE, modul="dispo"),
    _bereich("abrechnung", "Angebote & Rechnungen", zusatz=("freigeben",), modul="abrechnung"),
    _bereich("statistik", "Statistik & Exporte", modul="statistik"),
    _bereich(
        "mitarbeiterverwaltung", "Mitarbeiterliste", zusatz=("rechte_verwalten",), scopes=_VOLLE_KETTE
    ),
    _bereich("formulare", "Formular-Baukasten"),
    _bereich("partner", "Partner & Nachunternehmer", modul="nachunternehmer"),
    # Zeitplan: Techniker duerfen den Plan sehen und Aenderungen beantragen,
    # ohne projekte.sehen/bearbeiten (Kanban, Aufgaben, Vorlagen ...) zu bekommen.
    _bereich(
        "projekte",
        "Projekte",
        zusatz=("freigeben", "zeitplan_sehen", "zeitplan_beantragen"),
        scopes=_VOLLE_KETTE,
    ),
    _bereich("fehlerberichte", "Fehlerberichte", zusatz=("freigeben",)),
    _bereich("organigramm", "Organigramm", zusatz=("rechte_verwalten",), scopes=_VOLLE_KETTE),
)

_BEREICH_NACH_KEY: dict[str, RechteBereichDef] = {b.key: b for b in _BEREICHE}


def alle_bereiche() -> tuple[RechteBereichDef, ...]:
    return _BEREICHE


def alle_bereich_keys() -> tuple[str, ...]:
    return tuple(b.key for b in _BEREICHE)


def alle_aktionen() -> tuple[str, ...]:
    """Vereinigung aller Aktionen in stabiler Reihenfolge (Basis zuerst)."""
    gesehen: dict[str, None] = {}
    for bereich in _BEREICHE:
        for aktion in bereich.aktionen:
            gesehen.setdefault(aktion)
    return tuple(gesehen)


def aktionen_fuer_bereich(bereich: str) -> tuple[str, ...]:
    definition = _BEREICH_NACH_KEY.get(bereich)
    return definition.aktionen if definition else ()


def scopes_fuer_bereich(bereich: str) -> tuple[str, ...]:
    definition = _BEREICH_NACH_KEY.get(bereich)
    return definition.scopes if definition else ()


def ist_gueltig(bereich: str, aktion: str) -> bool:
    return aktion in aktionen_fuer_bereich(bereich)
