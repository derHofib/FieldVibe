"""Gemeinsame Maschine der *_speichern-Tools (Anlegen und Aendern in einem Tool, Konzept mcp-ausbau 5).

Je Objektart (`Art`) ist hier festgelegt, welche Felder ein Tool setzen darf, welche beim Anlegen Pflicht sind und
wie die Fachroute heisst. Der Ablauf ist fuer alle gleich:
- Anlegen: POST, danach ggf. ein PATCH fuer Felder, die die Create-Route nicht kennt (z. B. Zustaendiger). Rueckweg ist
  das Loeschen des neuen Datensatzes, solange er seit dem Anlegen unveraendert ist (Pruefung auf updated_at).
- Aendern: Vorher-Stand per GET, PATCH nur mit den uebergebenen Feldern (`felder_leeren` setzt gezielt auf null),
  Nachher-Stand aus der Antwort. Rueckweg ist ein PATCH mit den Vorher-Werten der tatsaechlich geaenderten Felder;
  je Feld wird vorab geprueft, dass es noch den Nachher-Wert hat.
Alles laeuft ueber die Fachrouten (Rechte, Scope, Module dort) und ueber das Journal (app/mcp/journal.py)."""
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from app.mcp.anzeige import EINGEBETTET, Namen, app_link, feld_label
from app.mcp.journal import Aktion, operation, pruefung
from app.mcp.oauth_provider import KiAccessToken
from app.mcp.rest_client import api_get, api_patch, api_post


def _unveraendert(obj: dict[str, Any]) -> dict[str, Any]:
    return obj


def _aufgabe_normalisieren(obj: dict[str, Any]) -> dict[str, Any]:
    # Die API kennt nur erledigt_am; fuer Tool und Anzeige ist "erledigt" ein Ja/Nein-Feld.
    return {**obj, "erledigt": obj.get("erledigt_am") is not None}


def _termin_entpacken(antwort: dict[str, Any]) -> dict[str, Any]:
    return antwort["termin"] if "termin" in antwort else antwort


@dataclass(frozen=True)
class Art:
    typ: str
    bezeichnung: str  # fuer Texte: "Vorgang", "Kontakt vor Ort"
    basis: str  # Basis-Pfad der Fachroute; Detail unter basis/{id}
    felder: tuple[str, ...]
    pflicht: tuple[str, ...]  # beim Anlegen Pflicht
    anlegen_felder: tuple[str, ...]  # Felder, die die Create-Route kennt; der Rest geht in einen Folge-PATCH
    label: Callable[[dict[str, Any]], str]
    extra_felder: tuple[str, ...] = ()  # nur im Body (z. B. wiedervorlage_tage), nicht verglichen/journalisiert
    vorgabe: dict[str, Any] = field(default_factory=dict)  # Standardwerte beim Anlegen
    entpacken: Callable[[dict[str, Any]], dict[str, Any]] = _unveraendert
    normalisieren: Callable[[dict[str, Any]], dict[str, Any]] = _unveraendert
    # Pruefung vor dem Rueckgaengig: API-Feld, das den Tool-Feldnamen ersetzt (aufgabe: erledigt -> erledigt_am)
    pruef_feld: dict[str, str] = field(default_factory=dict)
    kontakt: bool = False  # Kontakt vor Ort: keine Einzel-GET-Route, Zugriff ueber die Kontaktliste des Kunden


def _vorgang_label(o: dict[str, Any]) -> str:
    return f"{o.get('vorgangsnummer') or ''} {o.get('titel') or ''}".strip()


ARTEN: dict[str, Art] = {
    "vorgang": Art(
        "vorgang",
        "Vorgang",
        "/api/vorgaenge",
        (
            "titel",
            "beschreibung",
            "kunde_id",
            "anlage_id",
            "standort_id",
            "leistungstyp",
            "abrechnungsart",
            "prioritaet",
            "faelligkeit_am",
            "zugewiesener_user_id",
            "status",
        ),
        ("kunde_id", "titel", "leistungstyp"),
        ("kunde_id", "titel", "beschreibung", "leistungstyp", "abrechnungsart", "prioritaet", "anlage_id", "standort_id", "faelligkeit_am"),
        _vorgang_label,
        extra_felder=("wiedervorlage_tage",),
        vorgabe={"abrechnungsart": "aufwand"},
    ),
    "auftrag": Art(
        "auftrag",
        "Auftrag",
        "/api/auftraege",
        ("titel", "beschreibung", "kunde_id", "projekt_id", "standort_id", "einheit", "kunden_referenz", "status"),
        ("titel",),
        ("titel", "beschreibung", "kunde_id", "projekt_id", "standort_id", "einheit", "kunden_referenz"),
        lambda o: o.get("titel") or "",
    ),
    "projekt": Art(
        "projekt",
        "Projekt",
        "/api/projekte",
        ("name", "beschreibung", "kunde_id", "standort_id"),
        ("name",),
        ("name", "beschreibung", "kunde_id", "standort_id"),
        lambda o: o.get("name") or "",
    ),
    "aufgabe": Art(
        "aufgabe",
        "Aufgabe",
        "/api/projekt-aufgaben",
        (
            "titel",
            "beschreibung",
            "projekt_id",
            "spalte_id",
            "faelligkeit_am",
            "prioritaet",
            "zugewiesen_an",
            "erledigt",
            "vorgang_id",
            "auftrag_id",
        ),
        ("titel",),
        ("titel", "beschreibung", "projekt_id", "spalte_id", "faelligkeit_am", "prioritaet", "zugewiesen_an", "vorgang_id", "auftrag_id"),
        lambda o: o.get("titel") or "",
        normalisieren=_aufgabe_normalisieren,
        pruef_feld={"erledigt": "erledigt_am"},
    ),
    "termin": Art(
        "termin",
        "Termin",
        "/api/termine",
        ("titel", "vorgang_id", "techniker_id", "start_at", "ende_at", "notiz", "fahrzeit_minuten", "pause_minuten", "status"),
        ("vorgang_id", "techniker_id", "titel", "start_at", "ende_at"),
        ("vorgang_id", "techniker_id", "titel", "start_at", "ende_at", "notiz", "fahrzeit_minuten", "pause_minuten"),
        lambda o: o.get("titel") or "",
        entpacken=_termin_entpacken,
    ),
    "kunde": Art(
        "kunde",
        "Kunde",
        "/api/kunden",
        ("name", "typ", "adresse", "notiz"),
        ("name",),
        ("name", "typ", "adresse", "notiz"),
        lambda o: o.get("name") or "",
    ),
    "standort": Art(
        "standort",
        "Standort",
        "/api/standorte",
        ("kunde_id", "bezeichnung", "adresse", "aktiv"),
        ("kunde_id", "bezeichnung"),
        ("kunde_id", "bezeichnung", "adresse"),
        lambda o: o.get("bezeichnung") or "",
        vorgabe={"adresse": {}},
    ),
    "kontakt_vor_ort": Art(
        "kontakt_vor_ort",
        "Kontakt vor Ort",
        "/api/vor-ort-kontakte",
        ("standort_id", "name", "rolle", "einheit", "telefon", "telefon2", "email", "erreichbarkeit", "hinweis"),
        ("rolle",),
        ("standort_id", "name", "rolle", "einheit", "telefon", "telefon2", "email", "erreichbarkeit", "hinweis"),
        lambda o: o.get("name") or o.get("telefon") or "Kontakt",
        kontakt=True,
    ),
}


def _detail_pfad(art: Art, id_: Any, kunde_id: Any = None) -> str:
    if art.kontakt:
        return f"/api/kunden/{kunde_id}/vor-ort-kontakte"
    return f"{art.basis}/{id_}"


async def _holen(z: KiAccessToken, art: Art, id_: Any, kunde_id: Any = None) -> dict[str, Any]:
    if art.kontakt:
        if not kunde_id:
            raise ToolError("Für Kontakte vor Ort bitte kunde_id angeben (suchen liefert sie zum Kontakt).")
        liste = await api_get(z, _detail_pfad(art, id_, kunde_id))
        treffer = next((k for k in liste if str(k.get("id")) == str(id_)), None)
        if treffer is None:
            raise ToolError("Nicht gefunden: Dieser Kontakt gehört nicht zum angegebenen Kunden oder existiert nicht.")
        return art.normalisieren(treffer)
    return art.normalisieren(art.entpacken(await api_get(z, _detail_pfad(art, id_))))


def pruef_pfad_und_element(art: Art, id_: Any, kunde_id: Any) -> tuple[str, tuple[str, Any] | None]:
    if art.kontakt:
        return _detail_pfad(art, id_, kunde_id), ("id", str(id_))
    return _detail_pfad(art, id_), None


async def speichern(
    z: KiAccessToken,
    art: Art,
    *,
    tool: str,
    id_: str | None,
    werte: dict[str, Any],
    leeren: list[str] | None = None,
    kunde_id: str | None = None,
) -> dict[str, Any]:
    """Legt an (id_ None) oder aendert. `werte` enthaelt nur uebergebene Felder (nicht None)."""
    leeren = list(dict.fromkeys(leeren or []))
    erlaubt = {*art.felder, *art.extra_felder}
    falsch = [f for f in leeren if f not in art.felder or f in art.pflicht]
    if falsch:
        moegliche = [f for f in art.felder if f not in art.pflicht]
        raise ToolError(f"felder_leeren: {', '.join(falsch)} lässt sich nicht leeren. Möglich: {', '.join(moegliche)}.")
    doppelt = [f for f in leeren if f in werte]
    if doppelt:
        raise ToolError(f"Widerspruch: {', '.join(doppelt)} soll gesetzt und gleichzeitig geleert werden.")
    unbekannt = [f for f in werte if f not in erlaubt]
    if unbekannt:  # Programmierfehler eines Tools, kein Nutzerfehler
        raise ValueError(f"Unbekannte Felder fuer {art.typ}: {unbekannt}")
    if id_ is None:
        if leeren:
            raise ToolError("felder_leeren gibt es nur beim Ändern (mit id).")
        return await _anlegen(z, art, tool=tool, werte=werte, kunde_id=kunde_id)
    if not werte and not leeren:
        raise ToolError("Es gibt nichts zu ändern: bitte mindestens ein Feld angeben (oder felder_leeren).")
    return await _aendern(z, art, tool=tool, id_=id_, werte=werte, leeren=leeren, kunde_id=kunde_id)


def _aufloesen_namen_merken(namen: Namen, art: Art, obj: dict[str, Any]) -> None:
    namen.merken(art.typ, obj.get("id"), art.label(obj))


async def _anlegen(z: KiAccessToken, art: Art, *, tool: str, werte: dict[str, Any], kunde_id: str | None) -> dict[str, Any]:
    fehlend = [feld_label(art.typ, f) for f in art.pflicht if werte.get(f) in (None, "")]
    if art.kontakt and not (werte.get("name") or werte.get("telefon")):
        fehlend.append("Name oder Telefon")
    if art.kontakt and not kunde_id:
        fehlend.append("Kunde (kunde_id)")
    if fehlend:
        raise ToolError(f"Zum Anlegen fehlt: {', '.join(fehlend)}.")
    create = {**art.vorgabe, **{f: v for f, v in werte.items() if f in art.anlegen_felder}}
    nachtrag = {f: v for f, v in werte.items() if f not in art.anlegen_felder}
    pfad = f"/api/kunden/{kunde_id}/vor-ort-kontakte" if art.kontakt else art.basis
    namen = Namen(z)
    aktion = Aktion(z, tool=tool, aktionsart=f"{art.typ}.anlegen", stufe=1)
    warnungen: list[Any] = []
    fehler: str | None = None
    with aktion:
        antwort = await api_post(z, pfad, create)
        warnungen = antwort.get("warnungen", []) if "termin" in antwort else []
        erstellt = art.normalisieren(art.entpacken(antwort))
        id_ = erstellt["id"]
        label = art.label(erstellt)
        _aufloesen_namen_merken(namen, art, erstellt)
        aktion.neu_erzeugt(art.typ, id_, label)
        aktuell = erstellt
        if nachtrag:
            try:
                aktuell = art.normalisieren(
                    art.entpacken(await api_patch(z, f"{art.basis}/{id_}", {k: v for k, v in nachtrag.items()}))
                )
            except ToolError as exc:
                fehler = f"Der Datensatz wurde angelegt, aber {', '.join(feld_label(art.typ, f) for f in nachtrag)} konnte nicht gesetzt werden: {exc}"
        # Stand nach allem; daran misst das Rueckgaengig "seit dem Anlegen unveraendert".
        frisch = aktuell
        if not art.kontakt:
            try:
                frisch = art.normalisieren(art.entpacken(await api_get(z, f"{art.basis}/{id_}")))
            except ToolError:  # der Datensatz existiert schon; ein Lesefehler darf das Journal nicht verhindern
                pass
        for f in nachtrag:
            if f in art.felder and fehler is None:
                await aktion.vergleichen(namen, art.typ, id_, label, {}, aktuell, [f])
        pruefungen = []
        pfad_pruef, element = pruef_pfad_und_element(art, id_, kunde_id)
        for feld in ("updated_at",):
            pruefungen.append(
                pruefung(pfad_pruef, feld, frisch.get(feld), label=label, feld_label="Zuletzt geändert", element=element)
            )
        aktion.rueckweg_hinzu(operation("DELETE", f"{art.basis}/{id_}", None, pruefungen))
        zusammenfassung = f"{art.bezeichnung} „{label}“ angelegt"
        link = app_link(art.typ, id_, frisch)
    extra = {"warnungen": warnungen} if warnungen else None
    return await aktion.fertig(zusammenfassung, link=link, fehler=fehler, extra=extra)


async def _aendern(
    z: KiAccessToken,
    art: Art,
    *,
    tool: str,
    id_: str,
    werte: dict[str, Any],
    leeren: list[str],
    kunde_id: str | None,
) -> dict[str, Any]:
    vorher = await _holen(z, art, id_, kunde_id)
    body = {**werte, **{f: None for f in leeren}}
    namen = Namen(z)
    label = art.label(vorher)
    _aufloesen_namen_merken(namen, art, vorher)
    aktion = Aktion(z, tool=tool, aktionsart=f"{art.typ}.aendern", stufe=2)
    warnungen: list[Any] = []
    with aktion:
        antwort = await api_patch(z, f"{art.basis}/{id_}", body)
        warnungen = antwort.get("warnungen", []) if "termin" in antwort else []
        nachher = art.normalisieren(art.entpacken(antwort))
        if art.kontakt:  # PATCH liefert hier schon den Kontakt
            nachher = art.normalisieren(antwort)
        label = art.label(nachher) or label
        aktion.ziel(art.typ, id_, label)
        felder = [f for f in art.felder if f in body]
        geaendert = await aktion.vergleichen(namen, art.typ, id_, label, vorher, nachher, felder)
        if not geaendert:
            return {
                "aktion_id": None,
                "zusammenfassung": f"{art.bezeichnung} „{label}“ bleibt unverändert: Die Werte entsprachen schon dem aktuellen Stand.",
                "aenderungen": [],
                "erzeugt": [],
                "link": app_link(art.typ, id_, nachher),
                "rueckgaengig_bis": None,
            }
        rueck_body = {f: vorher.get(f) for f in geaendert}
        pfad_pruef, element = pruef_pfad_und_element(art, id_, kunde_id)
        pruefungen = [
            pruefung(
                pfad_pruef,
                art.pruef_feld.get(f, f),
                nachher.get("erledigt_am") if f in art.pruef_feld else nachher.get(f),
                label=label,
                feld_label=feld_label(art.typ, f),
                erwartet_anzeige=await namen.anzeige(f, nachher.get(f), nachher),
                anzeige_feld=EINGEBETTET.get(f),
                element=element,
            )
            for f in geaendert
        ]
        aktion.rueckweg_hinzu(operation("PATCH", f"{art.basis}/{id_}", rueck_body, pruefungen))
        zusammenfassung = f"{art.bezeichnung} „{label}“ geändert: {', '.join(feld_label(art.typ, f) for f in geaendert)}"
        link = app_link(art.typ, id_, nachher)
    extra = {"warnungen": warnungen} if warnungen else None
    return await aktion.fertig(zusammenfassung, link=link, extra=extra)

