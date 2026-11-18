"""Antwort-Aufbereitung fuer Tool-Ergebnisse (Datensparsamkeit, siehe docs/MCP.md):
sensible Felder entfernen und Listen begrenzen, damit keine Komplett-Abzuege entstehen."""
import re
from typing import Any

SEITENGROESSE = 100

# Schluesselnamen, deren Werte nie an den KI-Anbieter gehen (Bankdaten, Zugangsdaten,
# signierte Datei-Links, die nach Minuten ablaufen und dem Modell nichts nuetzen).
_SENSIBEL = re.compile(r"(^|_)(iban|bic)($|_)|passwor|mfa|token|secret|hash|_url$", re.IGNORECASE)


def bereinigen(wert: Any) -> Any:
    """Entfernt rekursiv Felder mit sensiblem Namen."""
    if isinstance(wert, dict):
        return {k: bereinigen(v) for k, v in wert.items() if not _SENSIBEL.search(str(k))}
    if isinstance(wert, list):
        return [bereinigen(v) for v in wert]
    return wert


def seite_aus(
    eintraege: list[Any], seite: int, *, quelle_abgeschnitten: bool = False
) -> dict[str, Any]:
    """Eine Seite zu max. SEITENGROESSE Eintraegen. quelle_abgeschnitten: die API selbst hat
    ihre Liste schon begrenzt (z. B. limit=200) -- dann gibt es evtl. weitere Eintraege, die
    nur ueber engere Filter erreichbar sind."""
    seite = max(1, seite)
    start = (seite - 1) * SEITENGROESSE
    teil = eintraege[start : start + SEITENGROESSE]
    ergebnis: dict[str, Any] = {
        "eintraege": bereinigen(teil),
        "seite": seite,
        "anzahl_gesamt": len(eintraege),
        "gekuerzt": start + SEITENGROESSE < len(eintraege),
    }
    hinweise = []
    if ergebnis["gekuerzt"]:
        hinweise.append(f"Weitere Einträge mit seite={seite + 1} abrufen.")
    if quelle_abgeschnitten and start + SEITENGROESSE >= len(eintraege):
        hinweise.append(
            "Die Liste ist an der Obergrenze der Schnittstelle abgeschnitten; "
            "weitere Einträge nur über engere Filter erreichbar."
        )
    if teil == [] and start > 0:
        hinweise.append("Diese Seite ist leer.")
    if hinweise:
        ergebnis["hinweis"] = " ".join(hinweise)
    return ergebnis
