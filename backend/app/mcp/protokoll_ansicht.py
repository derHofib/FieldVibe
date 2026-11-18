"""Lesbare Aufbereitung eines Protokolls (form_submission) fuer Claude: nach Abschnitten gruppierte Werte mit
Beschriftungen, Grenzwert-Markierung und fehlenden Pflichtfeldern -- reine Logik ohne I/O.

Dieselben Daten gehen als Text (formular_lesen, protokoll_anzeigen ohne MCP Apps) und als structuredContent an die
HTML-Ansicht (ui://fieldvibe/protokoll.html). Fotos, Unterschriften und Dateien erscheinen nur als Hinweis bzw.
Anzahl: signierte Links und Storage-Keys gehen nie in den Chat."""
from typing import Any

from app.mcp.protokoll_werte import fehlende_pflichtfelder
from app.services.form_grenzwert import grenzwert_abweichung, grenzwert_text

_DATEI_TYPEN = ("foto", "unterschrift", "datei", "foto_plan")


def _label(obj: dict[str, Any]) -> str:
    return (obj.get("label") or {}).get("de") or obj["key"]


def _leer(wert: Any) -> bool:
    return wert is None or wert == "" or wert == [] or wert == {}


def _hat_foto(typ: str, wert: Any) -> bool:
    if typ == "foto_plan":
        return isinstance(wert, dict) and bool(wert.get("foto"))
    return typ == "foto" and isinstance(wert, dict) and bool(wert)


def _anzeige(feld: dict[str, Any], wert: Any) -> str:
    typ = feld["feld_typ"]
    if _leer(wert):
        return "—"
    if typ == "ja_nein":
        return "Ja" if wert else "Nein"
    if typ == "foto":
        return "Foto vorhanden"
    if typ == "foto_plan":
        return "Foto mit Markierungen vorhanden" if _hat_foto(typ, wert) else "—"
    if typ == "unterschrift":
        return "Unterschrift vorhanden"
    if typ == "datei":
        name = wert.get("filename") if isinstance(wert, dict) else None
        return name or "Datei hinterlegt"
    if typ == "gps" and isinstance(wert, dict) and {"lat", "lng"} <= set(wert):
        return f"{float(wert['lat']):.6f}, {float(wert['lng']):.6f}"
    if typ == "adresse" and isinstance(wert, dict):
        ort = " ".join(str(wert[k]) for k in ("plz", "ort") if wert.get(k))
        return ", ".join(t for t in (wert.get("strasse"), ort) if t) or "—"
    if typ == "betrag":
        try:
            return f"{float(wert):.2f}".replace(".", ",") + " €"
        except (TypeError, ValueError):
            return str(wert)
    if typ == "zahl":
        return str(wert).replace(".", ",")
    if isinstance(wert, list):
        return ", ".join(str(w) for w in wert)
    return str(wert)


def _feld_eintrag(feld: dict[str, Any], wert: Any) -> dict[str, Any]:
    eintrag: dict[str, Any] = {
        "label": _label(feld),
        "typ": feld["feld_typ"],
        "pflicht": bool(feld.get("pflichtfeld")),
        "anzeige": _anzeige(feld, wert),
        "leer": _leer(wert) or (feld["feld_typ"] == "foto_plan" and not _hat_foto("foto_plan", wert)),
    }
    if feld["feld_typ"] not in _DATEI_TYPEN and not _leer(wert):
        eintrag["wert"] = wert
    abweichung = grenzwert_abweichung(feld["feld_typ"], feld.get("validation"), wert)
    if abweichung:
        eintrag["grenzwert"] = {"richtung": abweichung[0], "grenze": abweichung[1], "text": grenzwert_text(abweichung)}
    return eintrag


def abschnitte_aus(schema: dict[str, Any], werte: dict[str, Any]) -> list[dict[str, Any]]:
    """Werte gruppiert nach Abschnitten der Vorlage (Reihenfolge der Vorlage). Felder ohne Abschnitt kommen zuerst
    unter „Allgemein“; ein wiederholbarer Abschnitt hat je Eintrag eine Zeile, ein einfacher genau eine."""
    felder = sorted(schema["fields"], key=lambda f: f["reihenfolge"])
    abschnitte: list[dict[str, Any]] = []

    lose = [f for f in felder if f["group_key"] is None]
    if lose:
        abschnitte.append(
            {"titel": "Allgemein", "wiederholbar": False, "eintraege": [{"felder": [_feld_eintrag(f, werte.get(f["key"])) for f in lose]}]}
        )
    for gruppe in sorted(schema["groups"], key=lambda g: g["reihenfolge"]):
        gruppen_felder = [f for f in felder if f["group_key"] == gruppe["key"]]
        zeilen = werte.get(gruppe["key"])
        zeilen = [z for z in zeilen if isinstance(z, dict)] if isinstance(zeilen, list) else []
        if not gruppe["repeatable"]:
            zeilen = zeilen[:1] or [{}]
        eintraege = [{"felder": [_feld_eintrag(f, z.get(f["key"])) for f in gruppen_felder]} for z in zeilen]
        abschnitte.append({"titel": _label(gruppe), "wiederholbar": bool(gruppe["repeatable"]), "eintraege": eintraege})
    return abschnitte


def fotos_anzahl(schema: dict[str, Any], werte: dict[str, Any]) -> int:
    anzahl = 0
    for feld in schema["fields"]:
        if feld["feld_typ"] not in ("foto", "foto_plan"):
            continue
        if feld["group_key"] is None:
            anzahl += _hat_foto(feld["feld_typ"], werte.get(feld["key"]))
        else:
            zeilen = werte.get(feld["group_key"])
            anzahl += sum(
                _hat_foto(feld["feld_typ"], z.get(feld["key"])) for z in (zeilen if isinstance(zeilen, list) else []) if isinstance(z, dict)
            )
    return int(anzahl)


def protokoll_ansicht(
    schema: dict[str, Any], protokoll: dict[str, Any], vorgang: dict[str, Any] | None, link: str
) -> dict[str, Any]:
    """structuredContent von protokoll_anzeigen: alles, was die HTML-Ansicht braucht, und nichts darueber hinaus."""
    werte = protokoll["values"]
    return {
        "art": "protokoll",
        "id": protokoll["id"],
        "vorlage": schema["name"],
        "version": protokoll["schema_version"],
        "status": protokoll["status"],
        "erstellt_via": protokoll.get("erstellt_via", "app"),
        "abgeschlossen_am": protokoll.get("abgeschlossen_am"),
        "vorgang": (
            {"id": vorgang["id"], "nummer": vorgang.get("vorgangsnummer"), "titel": vorgang.get("titel")} if vorgang else None
        ),
        "abschnitte": abschnitte_aus(schema, werte),
        "fehlende_pflichtfelder": fehlende_pflichtfelder(schema, werte),
        "fotos_anzahl": fotos_anzahl(schema, werte),
        "link": link,
    }


def protokoll_text(ansicht: dict[str, Any]) -> str:
    """Dieselben Inhalte als Text fuer Clients ohne MCP Apps (und fuer das Modell)."""
    kopf = f"Protokoll „{ansicht['vorlage']}“ (Version {ansicht['version']}), Status {ansicht['status']}"
    if ansicht["vorgang"]:
        kopf += f", Vorgang {ansicht['vorgang'].get('nummer') or ''} {ansicht['vorgang'].get('titel') or ''}".rstrip()
    if ansicht["erstellt_via"] == "ki":
        kopf += ", von Claude angelegt"
    zeilen = [kopf + "."]
    for abschnitt in ansicht["abschnitte"]:
        zeilen.append(f"\n{abschnitt['titel']}")
        for nr, eintrag in enumerate(abschnitt["eintraege"], start=1):
            if abschnitt["wiederholbar"]:
                zeilen.append(f"  Eintrag {nr}")
            for f in eintrag["felder"]:
                markierung = f" ⚠ {f['grenzwert']['text']}" if "grenzwert" in f else ""
                zeilen.append(f"  - {f['label']}: {f['anzeige']}{markierung}")
    if ansicht["fotos_anzahl"]:
        zeilen.append(f"\nFotos: {ansicht['fotos_anzahl']} (nur in der App sichtbar).")
    if ansicht["fehlende_pflichtfelder"]:
        zeilen.append(f"\nNoch fehlende Pflichtfelder: {', '.join(ansicht['fehlende_pflichtfelder'])}.")
    zeilen.append(f"\nIn FieldVibe öffnen: {ansicht['link']}")
    return "\n".join(zeilen)
