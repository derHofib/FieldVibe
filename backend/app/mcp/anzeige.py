"""Lesbare Anzeige fuer das KI-Journal: Feldbeschriftungen, Werte (Datum, Ja/Nein, Adresse) und das Aufloesen
von IDs zu Namen (Auftrag-Titel, Mitarbeiter ...) -- fuer die Aenderungs-Karte im Chat und die Seite
KI-Aktivitaet. Die rohen Werte bleiben im Journal erhalten (fuer das Rueckgaengig), hier entsteht nur die
Darstellung."""
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from mcp.server.mcpserver.exceptions import ToolError

from app.mcp.oauth_provider import KiAccessToken
from app.mcp.rest_client import api_get

# typ -> feld -> Beschriftung. Gleichzeitig die Liste der Felder, die ein *_speichern-Tool ueberhaupt kennt.
FELD_LABELS: dict[str, dict[str, str]] = {
    "vorgang": {
        "titel": "Titel",
        "beschreibung": "Beschreibung",
        "kunde_id": "Kunde",
        "anlage_id": "Anlage",
        "standort_id": "Standort",
        "leistungstyp": "Leistungstyp",
        "abrechnungsart": "Abrechnungsart",
        "prioritaet": "Priorität",
        "faelligkeit_am": "Fälligkeit",
        "zugewiesener_user_id": "Zuständig",
        "status": "Status",
        "auftrag_id": "Auftrag",
        "projekt_id": "Projekt",
    },
    "auftrag": {
        "titel": "Titel",
        "beschreibung": "Beschreibung",
        "kunde_id": "Kunde",
        "projekt_id": "Projekt",
        "standort_id": "Standort",
        "einheit": "Einheit",
        "kunden_referenz": "Ihr Zeichen",
        "status": "Status",
    },
    "projekt": {
        "name": "Name",
        "beschreibung": "Beschreibung",
        "kunde_id": "Kunde",
        "standort_id": "Standort",
    },
    "aufgabe": {
        "titel": "Titel",
        "beschreibung": "Beschreibung",
        "projekt_id": "Projekt",
        "spalte_id": "Spalte",
        "faelligkeit_am": "Fälligkeit",
        "prioritaet": "Priorität",
        "zugewiesen_an": "Zuständig",
        "erledigt": "Erledigt",
        "vorgang_id": "Vorgang",
        "auftrag_id": "Auftrag",
    },
    "termin": {
        "vorgang_id": "Vorgang",
        "techniker_id": "Techniker",
        "titel": "Titel",
        "start_at": "Beginn",
        "ende_at": "Ende",
        "notiz": "Notiz",
        "fahrzeit_minuten": "Fahrzeit (Min.)",
        "pause_minuten": "Pause (Min.)",
        "status": "Status",
    },
    "kunde": {"name": "Name", "typ": "Kundentyp", "adresse": "Adresse", "notiz": "Notiz"},
    "standort": {"kunde_id": "Kunde", "bezeichnung": "Bezeichnung", "adresse": "Adresse", "aktiv": "Aktiv"},
    "kontakt_vor_ort": {
        "standort_id": "Standort",
        "name": "Name",
        "rolle": "Rolle",
        "einheit": "Einheit",
        "telefon": "Telefon",
        "telefon2": "Telefon 2",
        "email": "E-Mail",
        "erreichbarkeit": "Erreichbarkeit",
        "hinweis": "Hinweis",
    },
    "anlage": {"anlage_id": "Anlage"},
    "formular": {"werte": "Werte"},
}

# Felder mit Verweis auf einen anderen Datensatz -> Art fuer das Aufloesen des Namens.
ID_ARTEN = {
    "kunde_id": "kunde",
    "standort_id": "standort",
    "anlage_id": "anlage",
    "projekt_id": "projekt",
    "auftrag_id": "auftrag",
    "vorgang_id": "vorgang",
    "zugewiesener_user_id": "user",
    "techniker_id": "user",
    "zugewiesen_an": "user",
}

# Name steht schon in der Antwort der Fachroute (kein zusaetzlicher Abruf noetig).
EINGEBETTET = {
    "zugewiesener_user_id": "zugewiesener_name",
    "auftrag_id": "auftrag_titel",
    "projekt_id": "projekt_name",
    "kunde_id": "kunde_name",
    "zugewiesen_an": "zugewiesener_name",
}

_ENUM_ANZEIGE = {
    "neu": "neu",
    "geplant": "geplant",
    "in_arbeit": "in Arbeit",
    "wartet_kunde": "wartet auf Kunde",
    "abgeschlossen": "abgeschlossen",
    "abgerechnet": "abgerechnet",
    "storniert": "storniert",
    "offen": "offen",
    "bestaetigt": "bestätigt",
    "abgesagt": "abgesagt",
}


def feld_label(typ: str, feld: str) -> str:
    return FELD_LABELS.get(typ, {}).get(feld, feld.replace("_", " ").capitalize())


_BERLIN = ZoneInfo("Europe/Berlin")


def _als_datum(wert: str) -> datetime | None:
    if len(wert) < 10 or wert[4] != "-" or wert[7] != "-":
        return None
    try:
        return datetime.fromisoformat(wert.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_wert(wert: Any) -> str | None:
    """Anzeigetext eines Rohwerts; leer (None, "") bleibt None, die Oberflaeche zeigt dann einen Strich."""
    if wert is None or wert == "" or wert == [] or wert == {}:
        return None
    if isinstance(wert, bool):
        return "ja" if wert else "nein"
    if isinstance(wert, dict):
        teile = [str(wert.get(k)) for k in ("strasse", "plz", "ort") if wert.get(k)]
        return ", ".join(teile) if teile else ", ".join(f"{k}: {v}" for k, v in wert.items() if v not in (None, ""))
    if isinstance(wert, list):
        return ", ".join(str(format_wert(w) or "") for w in wert)
    if isinstance(wert, str):
        if wert in _ENUM_ANZEIGE:
            return _ENUM_ANZEIGE[wert]
        datum = _als_datum(wert)
        if datum is not None:
            if len(wert) == 10:
                return datum.strftime("%d.%m.%Y")
            lokal = datum.astimezone(_BERLIN) if datum.tzinfo else datum
            return lokal.strftime("%d.%m.%Y") if (lokal.hour, lokal.minute) == (0, 0) else lokal.strftime("%d.%m.%Y %H:%M")
    return str(wert)


def gleich(a: Any, b: Any) -> bool:
    """Vergleich fuer Journal und Rueckgaengig-Pruefung: IDs als Text, Zeitpunkte als Zeitpunkte (die API
    liefert dieselbe Zeit je nach Route mal mit Z, mal mit +00:00), Leerstring gleich None."""
    if a in (None, "") and b in (None, ""):
        return True
    if a is None or b is None:
        return False
    if isinstance(a, str) and isinstance(b, str):
        da, db = _als_datum(a), _als_datum(b)
        if da is not None and db is not None and len(a) > 10 and len(b) > 10:
            return da == db
        return a == b
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    return str(a) == str(b)


def eintrag(wert: Any, anzeige: str | None) -> dict[str, Any]:
    return {"wert": wert, "anzeige": anzeige}


class Namen:
    """Loest IDs zu Namen auf (mit Zwischenspeicher je Tool-Aufruf). Fehlt das Recht oder der Datensatz, bleibt es
    beim Rohwert -- die Anzeige ist nur Komfort."""

    def __init__(self, zugriff: KiAccessToken) -> None:
        self._z = zugriff
        self._cache: dict[tuple[str, str], str | None] = {}
        self._benutzer: dict[str, str] | None = None

    async def _holen(self, art: str, id_: str) -> str | None:
        try:
            if art == "kunde":
                return (await api_get(self._z, f"/api/kunden/{id_}")).get("name")
            if art == "standort":
                return (await api_get(self._z, f"/api/standorte/{id_}")).get("bezeichnung")
            if art == "anlage":
                return (await api_get(self._z, f"/api/anlagen/{id_}")).get("bezeichnung")
            if art == "projekt":
                return (await api_get(self._z, f"/api/projekte/{id_}")).get("name")
            if art == "auftrag":
                return (await api_get(self._z, f"/api/auftraege/{id_}")).get("titel")
            if art == "vorgang":
                v = await api_get(self._z, f"/api/vorgaenge/{id_}")
                return f"{v.get('vorgangsnummer')} {v.get('titel')}".strip()
            if art == "user":
                if self._benutzer is None:
                    liste = await api_get(self._z, "/api/users/auswahl")
                    self._benutzer = {u["id"]: u["name"] for u in liste}
                return self._benutzer.get(id_)
        except (ToolError, AttributeError, KeyError, TypeError):
            if art == "user" and self._benutzer is None:
                self._benutzer = {}
        return None

    def merken(self, art: str, id_: Any, name: str | None) -> None:
        if id_ and name:
            self._cache[(art, str(id_))] = name

    async def aufloesen(self, art: str, id_: Any) -> str | None:
        if id_ in (None, ""):
            return None
        schluessel = (art, str(id_))
        if schluessel not in self._cache:
            self._cache[schluessel] = await self._holen(art, str(id_))
        return self._cache[schluessel]

    async def anzeige(self, feld: str, wert: Any, objekt: dict[str, Any] | None = None) -> str | None:
        """Anzeigetext von `wert` fuer `feld`; `objekt` ist die Antwort der Fachroute, in der der Name oft schon steht."""
        if wert in (None, ""):
            return None
        art = ID_ARTEN.get(feld)
        if art is None:
            return format_wert(wert)
        eingebettet = (objekt or {}).get(EINGEBETTET.get(feld, ""))
        if eingebettet:
            self.merken(art, wert, eingebettet)
        return await self.aufloesen(art, wert) or str(wert)


def app_pfad(typ: str, id_: Any, objekt: dict[str, Any] | None = None) -> str:
    """Pfad der Detailansicht in der App (Office/Feld-App nutzen dieselben Routen)."""
    objekt = objekt or {}
    if typ in ("vorgang",):
        return f"/vorgaenge/{id_}"
    if typ in ("mangel", "kommentar"):
        return f"/vorgaenge/{objekt.get('vorgang_id') or id_}"
    if typ == "auftrag":
        return f"/auftraege?auftrag={id_}"
    if typ == "projekt":
        return f"/projekte?projekt={id_}"
    if typ == "aufgabe":
        return f"/projekte?projekt={objekt['projekt_id']}" if objekt.get("projekt_id") else f"/meine-aufgaben/{id_}"
    if typ == "kunde":
        return f"/kunden/{id_}"
    if typ == "kontakt_vor_ort":
        return f"/kunden/{objekt['kunde_id']}" if objekt.get("kunde_id") else "/kunden"
    if typ == "standort":
        return f"/standorte/{id_}"
    if typ == "anlage":
        return f"/anlagen/{id_}"
    if typ == "termin":
        return "/dispo"
    if typ == "telefonat":
        return "/telefonate"
    if typ == "formular":
        return f"/form-submissions/{id_}"
    if typ == "vorlage":
        return f"/form-schemas/{id_}"
    return "/"


def app_link(typ: str, id_: Any, objekt: dict[str, Any] | None = None) -> str:
    # frontend_base_url ist die Adresse, auf der der Nutzer ohnehin angemeldet ist (siehe protokolle.vorlagen_link).
    from app.core.config import get_settings

    return get_settings().frontend_base_url.rstrip("/") + app_pfad(typ, id_, objekt)
