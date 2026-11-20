"""Aktions-Registry des MCP-Adapters: welche schreibenden REST-Routen ein Tool aufrufen darf, mit Aktionsart und
Stufe (Konzept mcp-ausbau, Abschnitt 3 und 9).

Alles ist fail-closed: Was hier nicht steht, loest im rest_client einen PermissionError aus. Zwei getrennte
Listen:
- AKTIONEN: Routen, die Tools im normalen Ablauf aufrufen (Anlegen, Aendern, Verknuepfen). Kein DELETE.
- RUECKWEG_ROUTEN: Gegenoperationen fuers Rueckgaengig (DELETE, Zuordnung loesen). Nur mit rueckweg=True im
  rest_client, den ausschliesslich ki_rueckgaengig setzt; ein Tool kann sie nicht direkt aufrufen.
Stufe 3 (Senden, Abschliessen, Loeschen, Festschreiben) gibt es in Etappe A noch nicht."""
import re
from dataclasses import dataclass

UUID_MUSTER = r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}"

# Status, die per KI (noch) nicht gesetzt werden duerfen: abgeschlossen/storniert ist Stufe 3, abgerechnet setzt
# nur der Rechnungs-Workflow.
GESPERRTE_VORGANG_STATUS = frozenset({"abgeschlossen", "storniert", "abgerechnet"})


@dataclass(frozen=True)
class Route:
    methode: str
    pfad_muster: str
    aktionsart: str
    stufe: int

    @property
    def regex(self) -> re.Pattern[str]:
        return re.compile(self.pfad_muster)


def _r(methode: str, pfad: str, aktionsart: str, stufe: int) -> Route:
    return Route(methode, pfad.replace("{id}", UUID_MUSTER), aktionsart, stufe)


AKTIONEN: tuple[Route, ...] = (
    # --- Anlegen (Stufe 1) ---
    _r("POST", "/api/vorgaenge", "vorgang.anlegen", 1),
    _r("POST", "/api/auftraege", "auftrag.anlegen", 1),
    _r("POST", "/api/projekte", "projekt.anlegen", 1),
    _r("POST", "/api/projekt-aufgaben", "aufgabe.anlegen", 1),
    _r("POST", "/api/kunden", "kunde.anlegen", 1),
    _r("POST", "/api/standorte", "standort.anlegen", 1),
    _r("POST", "/api/kunden/{id}/vor-ort-kontakte", "kontakt_vor_ort.anlegen", 1),
    _r("POST", "/api/termine", "termin.anlegen", 1),
    _r("POST", "/api/vorgaenge/{id}/events", "kommentar.anlegen", 1),
    _r("POST", "/api/maengel", "mangel.anlegen", 1),
    _r("POST", "/api/telefonate", "telefonat.anlegen", 1),
    _r("POST", "/api/form-submissions", "protokoll.anlegen", 1),
    _r("POST", "/api/form-schemas", "vorlage.anlegen", 1),
    _r("POST", "/api/form-schemas/{id}/groups", "vorlage.aendern", 1),
    _r("POST", "/api/form-schemas/{id}/fields", "vorlage.aendern", 1),
    # Ansichten (Erfassung/Druck) nur anlegen, nie aendern oder loeschen: ohne Druckansicht scheitert das PDF
    # eines Protokolls. Wie die Felder-Routen nur auf Entwuerfen, die das Tool selbst entwirft/ueberarbeitet.
    _r("POST", "/api/form-schemas/{id}/views", "vorlage.aendern", 1),
    # --- Aendern (Stufe 2) ---
    _r("PATCH", "/api/vorgaenge/{id}", "vorgang.aendern", 2),
    _r("PATCH", "/api/auftraege/{id}", "auftrag.aendern", 2),
    _r("PATCH", "/api/projekte/{id}", "projekt.aendern", 2),
    _r("PATCH", "/api/projekt-aufgaben/{id}", "aufgabe.aendern", 2),
    _r("PATCH", "/api/kunden/{id}", "kunde.aendern", 2),
    _r("PATCH", "/api/standorte/{id}", "standort.aendern", 2),
    _r("PATCH", "/api/vor-ort-kontakte/{id}", "kontakt_vor_ort.aendern", 2),
    _r("PATCH", "/api/termine/{id}", "termin.aendern", 2),
    _r("PATCH", "/api/form-submissions/{id}", "protokoll.aendern", 2),
    _r("PATCH", "/api/form-schemas/{id}/fields/{id}", "vorlage.aendern", 2),
    # --- Verknuepfen (Stufe 2) ---
    _r("POST", "/api/vorgaenge/{id}/anlagen", "vorgang.verknuepfen", 2),
    _r("POST", "/api/vorgaenge/{id}/abhaengigkeiten", "vorgang.verknuepfen", 2),
    _r("POST", "/api/vorgaenge/{id}/vor-ort-kontakte", "kontakt_vor_ort.verknuepfen", 2),
    _r("POST", "/api/auftraege/{id}/vor-ort-kontakte", "kontakt_vor_ort.verknuepfen", 2),
    _r("POST", "/api/projekte/{id}/vor-ort-kontakte", "kontakt_vor_ort.verknuepfen", 2),
)

# Gegenoperationen fuers Rueckgaengig. Loeschen geht ueber den Papierkorb bzw. verwirft einen offenen Entwurf
# (Protokoll); die Fachrouten pruefen das Recht des Ausloesers selbst.
RUECKWEG_ROUTEN: tuple[Route, ...] = (
    _r("DELETE", "/api/vorgaenge/{id}", "vorgang.rueckgaengig", 1),
    _r("DELETE", "/api/auftraege/{id}", "auftrag.rueckgaengig", 1),
    _r("DELETE", "/api/projekte/{id}", "projekt.rueckgaengig", 1),
    _r("DELETE", "/api/projekt-aufgaben/{id}", "aufgabe.rueckgaengig", 1),
    _r("DELETE", "/api/kunden/{id}", "kunde.rueckgaengig", 1),
    _r("DELETE", "/api/standorte/{id}", "standort.rueckgaengig", 1),
    _r("DELETE", "/api/vor-ort-kontakte/{id}", "kontakt_vor_ort.rueckgaengig", 1),
    _r("DELETE", "/api/termine/{id}", "termin.rueckgaengig", 1),
    _r("DELETE", "/api/telefonate/{id}", "telefonat.rueckgaengig", 1),
    _r("DELETE", "/api/maengel/{id}", "mangel.rueckgaengig", 1),
    _r("DELETE", "/api/form-submissions/{id}", "protokoll.rueckgaengig", 1),
    _r("DELETE", "/api/vorgaenge/{id}/anlagen/{id}", "vorgang.verknuepfen_rueckgaengig", 2),
    _r("DELETE", "/api/vorgaenge/{id}/abhaengigkeiten/{id}", "vorgang.verknuepfen_rueckgaengig", 2),
    _r("DELETE", "/api/vor-ort-kontakt-zuordnungen/{id}", "kontakt_vor_ort.verknuepfen_rueckgaengig", 2),
)

_AKTIONEN_KOMPILIERT = tuple((r, r.regex) for r in AKTIONEN)
_RUECKWEG_KOMPILIERT = tuple((r, r.regex) for r in RUECKWEG_ROUTEN)


def _finde(liste, methode: str, pfad: str) -> Route | None:
    return next((r for r, regex in liste if r.methode == methode and regex.fullmatch(pfad)), None)


def aktion_fuer(methode: str, pfad: str) -> Route | None:
    return _finde(_AKTIONEN_KOMPILIERT, methode, pfad)


def schreibaufruf_erlaubt(methode: str, pfad: str) -> bool:
    return aktion_fuer(methode, pfad) is not None


def rueckweg_erlaubt(methode: str, pfad: str) -> bool:
    """Im Rueckweg-Modus gilt zusaetzlich zur normalen Liste die Rueckweg-Liste (Werte zuruecksetzen laeuft
    ueber dieselben PATCH-Routen wie das Aendern)."""
    return schreibaufruf_erlaubt(methode, pfad) or _finde(_RUECKWEG_KOMPILIERT, methode, pfad) is not None
