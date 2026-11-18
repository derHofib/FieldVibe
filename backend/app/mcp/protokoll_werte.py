"""Bildet die frei formulierten Werte, die Claude fuer ein Protokoll liefert, auf das Werte-Format
der Feld-App ab (form_submissions.values) -- reine Logik ohne I/O.

Format der Feld-App (siehe CaptureRenderer): Felder ohne Abschnitt liegen unter ihrem Key,
Abschnitte als Liste von Zeilen unter dem Gruppen-Key. Nicht wiederholbare Abschnitte haben genau eine
Zeile values[gruppe][0]. Zahl/Betrag liegen als String, Ja/Nein als bool, Mehrfachauswahl als Liste."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from app.mcp.vorlage_entwurf import norm

# Aufnahmen, Unterschriften, Dateien und Messwerte vom Geraet kann nur die App liefern.
NICHT_FUELLBAR = ("foto", "unterschrift", "datei", "gps", "qr_scan", "foto_plan")


def _label(obj: dict[str, Any]) -> str:
    return (obj.get("label") or {}).get("de") or obj["key"]


def _leer(wert: Any) -> bool:
    return wert is None or wert == "" or wert == [] or wert == {}


def _zahl(feld: dict[str, Any], wert: Any) -> str:
    if isinstance(wert, bool) or not isinstance(wert, (int, float, str)):
        raise ToolError(f"Feld „{_label(feld)}“ erwartet eine Zahl.")
    try:
        zahl = Decimal(str(wert).strip().replace(",", "."))
    except InvalidOperation:
        raise ToolError(f"Feld „{_label(feld)}“ erwartet eine Zahl, bekam „{wert}“.") from None
    if not zahl.is_finite():
        raise ToolError(f"Feld „{_label(feld)}“ erwartet eine endliche Zahl.")
    return format(zahl, "f")


def _datum(feld: dict[str, Any], wert: Any) -> str:
    text = str(wert).strip() if isinstance(wert, str) else ""
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    try:
        return (date(int(m[3]), int(m[2]), int(m[1])) if m else date.fromisoformat(text)).isoformat()
    except ValueError:
        raise ToolError(f"Feld „{_label(feld)}“ erwartet ein Datum (JJJJ-MM-TT oder TT.MM.JJJJ).") from None


def _option(feld: dict[str, Any], wert: Any) -> str:
    werte = (feld.get("optionen") or {}).get("werte") or []
    if not isinstance(wert, str):
        raise ToolError(f"Feld „{_label(feld)}“ erwartet einen Text aus der Auswahlliste.")
    if not werte:
        return wert
    for w in werte:
        if norm(w) == norm(wert):
            return w
    raise ToolError(f"Feld „{_label(feld)}“: „{wert}“ ist keine gültige Option. Erlaubt: {', '.join(werte)}.")


def konvertiere(feld: dict[str, Any], wert: Any) -> Any:
    typ = feld["feld_typ"]
    if typ in NICHT_FUELLBAR:
        raise ToolError(
            f"Das Feld „{_label(feld)}“ ({typ}) kann Claude nicht ausfüllen "
            "(Foto, Unterschrift, Datei, GPS, QR-Scan und Fotoplan nur in der App)."
        )
    if typ in ("text", "textarea", "email", "telefon"):
        if isinstance(wert, (dict, list)) or isinstance(wert, bool):
            raise ToolError(f"Feld „{_label(feld)}“ erwartet einen Text.")
        return str(wert)
    if typ in ("zahl", "betrag"):
        return _zahl(feld, wert)
    if typ == "datum":
        return _datum(feld, wert)
    if typ == "dropdown":
        return _option(feld, wert)
    if typ == "mehrfachauswahl":
        eintraege = wert if isinstance(wert, list) else [wert]
        gewaehlt = [_option(feld, e) for e in eintraege]
        return list(dict.fromkeys(gewaehlt))
    if typ == "ja_nein":
        if isinstance(wert, bool):
            return wert
        text = norm(str(wert))
        if text in ("ja", "true", "1", "j"):
            return True
        if text in ("nein", "false", "0", "n"):
            return False
        raise ToolError(f"Feld „{_label(feld)}“ erwartet Ja oder Nein (true/false).")
    if typ == "bewertung":
        opt = feld.get("optionen") or {}
        kleinste, groesste = int(opt.get("min", 1)), int(opt.get("max", 5))
        try:
            n = int(wert) if not isinstance(wert, bool) and float(wert) == int(float(wert)) else None
        except (TypeError, ValueError):
            n = None
        if n is None or not kleinste <= n <= groesste:
            raise ToolError(f"Feld „{_label(feld)}“ erwartet eine ganze Zahl von {kleinste} bis {groesste}.")
        return n
    if typ == "adresse":
        if not isinstance(wert, dict) or not set(wert) <= {"strasse", "plz", "ort"}:
            raise ToolError(f"Feld „{_label(feld)}“ erwartet ein Objekt mit strasse, plz und ort.")
        return {k: str(v) for k, v in wert.items()}
    raise ToolError(f"Feld „{_label(feld)}“ hat den Typ „{typ}“, den Claude nicht ausfüllen kann.")  # pragma: no cover


class _Katalog:
    def __init__(self, schema: dict[str, Any]) -> None:
        self.gruppen = {g["key"]: g for g in schema["groups"]}
        self.felder = {f["key"]: f for f in schema["fields"]}
        self.je_gruppe: dict[str | None, list[dict[str, Any]]] = {}
        for f in schema["fields"]:
            self.je_gruppe.setdefault(f["group_key"], []).append(f)

    def gruppe(self, name: str) -> dict[str, Any] | None:
        treffer = [g for g in self.gruppen.values() if name == g["key"] or norm(name) == norm(_label(g))]
        return treffer[0] if treffer else None

    def feld_in(self, gruppe_key: str | None, name: str) -> dict[str, Any] | None:
        for f in self.je_gruppe.get(gruppe_key, []):
            if name == f["key"] or norm(name) == norm(_label(f)):
                return f
        return None

    def feld_flach(self, name: str) -> list[dict[str, Any]]:
        """Felder ohne Abschnitt oder in nicht wiederholbaren Abschnitten (dort ist die Zeile eindeutig)."""
        return [
            f
            for f in self.felder.values()
            if (name == f["key"] or norm(name) == norm(_label(f)))
            and (f["group_key"] is None or not self.gruppen[f["group_key"]]["repeatable"])
        ]

    def gueltige_namen(self) -> str:
        zeilen = []
        for g in self.gruppen.values():
            art = "wiederholbarer Abschnitt, Liste von Einträgen" if g["repeatable"] else "Abschnitt"
            felder = ", ".join(
                f"{_label(f)} ({f['feld_typ']})" for f in self.je_gruppe.get(g["key"], []) if f["feld_typ"] not in NICHT_FUELLBAR
            )
            zeilen.append(f"{_label(g)} [{art}]: {felder or '-'}")
        offene = ", ".join(f"{_label(f)} ({f['feld_typ']})" for f in self.je_gruppe.get(None, []) if f["feld_typ"] not in NICHT_FUELLBAR)
        if offene:
            zeilen.append(f"Ohne Abschnitt: {offene}")
        return " | ".join(zeilen)


def _unbekannt(katalog: _Katalog, name: str, wo: str = "") -> ToolError:
    return ToolError(
        f"Unbekanntes Feld „{name}“{wo}. Gültig sind (Schlüssel oder Beschriftung): {katalog.gueltige_namen()}"
    )


def _zeile_abbilden(katalog: _Katalog, gruppe: dict[str, Any], zeile: Any) -> dict[str, Any]:
    if not isinstance(zeile, dict):
        raise ToolError(f"Abschnitt „{_label(gruppe)}“: jeder Eintrag muss ein Objekt aus Feld und Wert sein.")
    ergebnis: dict[str, Any] = {}
    for name, wert in zeile.items():
        feld = katalog.feld_in(gruppe["key"], str(name))
        if feld is None:
            raise _unbekannt(katalog, str(name), f" im Abschnitt „{_label(gruppe)}“")
        if wert is None:
            continue
        ergebnis[feld["key"]] = konvertiere(feld, wert)
    return ergebnis


def werte_abbilden(
    schema: dict[str, Any],
    werte: dict[str, Any],
    bestehend: dict[str, Any] | None = None,
    ueberschreiben: bool = False,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Liefert (zu schreibende Top-Level-Werte, gesetzte Felder, uebersprungene Felder).

    Additiv: ein bereits befuellter Wert bleibt, es sei denn `ueberschreiben`; wiederholbare
    Abschnitte bekommen die Eintraege angehaengt, bestehende Zeilen bleiben unveraendert."""
    katalog = _Katalog(schema)
    bestehend = bestehend or {}
    patch: dict[str, Any] = {}
    gesetzt: list[str] = []
    uebersprungen: list[str] = []

    def alte_zeile(gruppe_key: str) -> dict[str, Any]:
        vorhanden = bestehend.get(gruppe_key)
        return vorhanden[0] if isinstance(vorhanden, list) and vorhanden and isinstance(vorhanden[0], dict) else {}

    def gruppen_zeile(gruppe_key: str) -> dict[str, Any]:
        if gruppe_key not in patch:
            vorhanden = bestehend.get(gruppe_key)
            patch[gruppe_key] = [dict(alte_zeile(gruppe_key)), *(vorhanden[1:] if isinstance(vorhanden, list) else [])]
        return patch[gruppe_key][0]

    def setzen(ziel: dict[str, Any], feld: dict[str, Any], wert: Any, bisher: Any) -> None:
        if not _leer(bisher) and bisher != wert and not ueberschreiben:
            uebersprungen.append(_label(feld))
            return
        ziel[feld["key"]] = wert
        gesetzt.append(_label(feld))

    for name, wert in werte.items():
        name = str(name).strip()
        if wert is None:
            continue
        gruppe = katalog.gruppe(name)
        if gruppe is not None:
            if gruppe["repeatable"]:
                zeilen = wert if isinstance(wert, list) else [wert]
                vorhanden = bestehend.get(gruppe["key"])
                neue = [_zeile_abbilden(katalog, gruppe, z) for z in zeilen]
                patch[gruppe["key"]] = [*(vorhanden if isinstance(vorhanden, list) else []), *neue]
                gesetzt.extend(f"{_label(gruppe)} (Eintrag {i + 1})" for i in range(len(neue)))
            else:
                if not isinstance(wert, dict):
                    raise ToolError(f"Abschnitt „{_label(gruppe)}“ erwartet ein Objekt aus Feld und Wert.")
                zeile = gruppen_zeile(gruppe["key"])
                for feld_key, v in _zeile_abbilden(katalog, gruppe, wert).items():
                    setzen(zeile, katalog.felder[feld_key], v, alte_zeile(gruppe["key"]).get(feld_key))
            continue

        treffer = katalog.feld_flach(name)
        if len(treffer) > 1:
            raise ToolError(
                f"„{name}“ ist mehrdeutig (kommt in mehreren Abschnitten vor). Gib den Abschnitt an: "
                '{"Abschnittsname": {"Feld": Wert}}.'
            )
        if not treffer:
            wiederholbar = [
                f for f in katalog.felder.values()
                if (name == f["key"] or norm(name) == norm(_label(f))) and f["group_key"] is not None
            ]
            if wiederholbar:
                g = katalog.gruppen[wiederholbar[0]["group_key"]]
                raise ToolError(
                    f"Das Feld „{name}“ gehört zum wiederholbaren Abschnitt „{_label(g)}“. "
                    f'Gib eine Liste unter dem Abschnitt an: {{"{_label(g)}": [{{"{name}": Wert}}]}}.'
                )
            raise _unbekannt(katalog, name)
        feld = treffer[0]
        konvertiert = konvertiere(feld, wert)
        if feld["group_key"] is None:
            setzen(patch, feld, konvertiert, bestehend.get(feld["key"]))
        else:
            setzen(gruppen_zeile(feld["group_key"]), feld, konvertiert, alte_zeile(feld["group_key"]).get(feld["key"]))
    return patch, gesetzt, uebersprungen


def fehlende_pflichtfelder(schema: dict[str, Any], werte: dict[str, Any]) -> list[str]:
    """Hinweis fuer Claude/Nutzer, was vor dem Abschluss in der App noch fehlt (ohne Logik-Regeln und
    ohne Pflichtfelder in wiederholbaren Abschnitten, deren Zeilenzahl offen ist)."""
    katalog = _Katalog(schema)
    fehlt = []
    for f in schema["fields"]:
        if not f["pflichtfeld"]:
            continue
        if f["group_key"] is None:
            wert = werte.get(f["key"])
        else:
            if katalog.gruppen[f["group_key"]]["repeatable"]:
                continue
            zeilen = werte.get(f["group_key"])
            wert = zeilen[0].get(f["key"]) if isinstance(zeilen, list) and zeilen and isinstance(zeilen[0], dict) else None
        if _leer(wert):
            fehlt.append(_label(f))
    return fehlt
