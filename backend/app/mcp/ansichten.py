"""MCP Apps (mcp.server.apps): HTML-Ansichten im Claude-Chat (Konzept formulare, Abschnitt 6).

Die Ansichten liegen statisch im Paket (app/mcp/ui/), laden nichts nach und bekommen ihre Daten nur ueber das
Tool-Ergebnis (structuredContent). Clients ohne MCP Apps ignorieren die `_meta.ui`-Angabe und lesen den Text."""
from pathlib import Path
from typing import Any

from mcp.server.apps import Apps

PROTOKOLL_URI = "ui://fieldvibe/protokoll.html"
VORLAGE_URI = "ui://fieldvibe/vorlage.html"

_UI = Path(__file__).with_name("ui")


def _html(name: str) -> str:
    """Setzt Stil und Bruecken-Skript inline ein: ein einziges Dokument, keine externen Ressourcen."""
    return (
        (_UI / name)
        .read_text(encoding="utf-8")
        .replace("/*STIL*/", (_UI / "basis.css").read_text(encoding="utf-8"))
        .replace("/*BRUECKE*/", (_UI / "bruecke.js").read_text(encoding="utf-8"))
    )


def ui_meta(uri: str) -> dict[str, Any]:
    # "ui/resourceUri" ist die aeltere, flache Schreibweise, die manche Hosts noch erwarten.
    return {"ui": {"resourceUri": uri}, "ui/resourceUri": uri}


def baue_apps() -> Apps:
    apps = Apps()
    apps.add_html_resource(
        PROTOKOLL_URI,
        _html("protokoll.html"),
        name="protokoll_ansicht",
        title="Protokoll-Ansicht",
        description="Ausgefülltes Protokoll als Zusammenfassung (Abschnitte, Ja/Nein, Grenzwerte, fehlende Pflichtfelder).",
    )
    apps.add_html_resource(
        VORLAGE_URI,
        _html("vorlage.html"),
        name="vorlage_ansicht",
        title="Vorlagen-Entwurf",
        description="Entwurf einer Protokoll-Vorlage mit Abschnitten und Feldern.",
    )
    return apps
