"""Prompt-Vorlagen, die in Claude waehlbar sind. Sie geben nur Anweisungen vor; die Daten holen
die Tools mit den Rechten des Nutzers."""
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field


def registrieren(mcp: MCPServer) -> None:
    @mcp.prompt(
        name="protokoll_vorlage_entwerfen",
        title="Protokoll-Vorlage entwerfen",
        description=(
            "Entwirft eine neue Protokoll-Vorlage als Entwurf im Formular-Baukasten "
            "(nur mit Schreibzugriff und dem Recht Formulare › erstellen)."
        ),
    )
    def protokoll_vorlage_entwerfen(
        thema: Annotated[str, Field(description="Wofür ist das Protokoll? z. B. Wartung Gas-Brennwerttherme")],
        vorgaben: Annotated[str, Field(description="Optional: Herstellervorgaben, Grenzwerte, gewünschte Felder.")] = "",
    ) -> str:
        zusatz = f"\n\nZusätzliche Vorgaben des Nutzers:\n{vorgaben}" if vorgaben.strip() else ""
        return (
            f"Entwirf in FieldVibe eine Protokoll-Vorlage zum Thema: {thema}.{zusatz}\n\n"
            "Vorgehen:\n"
            "1. Prüfe mit auflisten (typ=\"vorlage\"), ob es schon eine passende Vorlage gibt; lies sie bei Bedarf mit "
            "lesen (typ=\"vorlage\") und schlage dann eine Variante statt eines Duplikats vor.\n"
            "2. Gliedere sinnvoll in Abschnitte: Kopf/Anlagendaten, Prüfpunkte (z. B. ja_nein oder dropdown), "
            "Messwerte (zahl, mit Grenzwert im hilfetext), Mängel (wiederholbarer Abschnitt mit Beschreibung und Foto), "
            "Abschluss mit Unterschrift Kunde und Techniker. Pflicht nur dort, wo ohne Wert das Protokoll wertlos wäre.\n"
            "3. Zeige dem Nutzer kurz die geplante Gliederung und lege sie dann mit vorlage_entwurf an.\n"
            "4. Weise darauf hin, dass es ein Entwurf ist: Prüfen, Veröffentlichen und die Zuordnung zum Leistungstyp "
            "macht der Nutzer im Formular-Baukasten (Link aus dem Ergebnis)."
        )

    @mcp.prompt(
        name="wartungsprotokoll_zu_vorgang_ausfuellen",
        title="Wartungsprotokoll zu Vorgang ausfüllen",
        description="Füllt aus Stichpunkten ein Protokoll-Entwurf zu einem Vorgang (nur mit Schreibzugriff).",
    )
    def wartungsprotokoll_zu_vorgang_ausfuellen(
        vorgang_id: Annotated[str, Field(description="ID des Vorgangs")],
    ) -> str:
        return (
            f"Erstelle einen Protokoll-Entwurf für den Vorgang {vorgang_id}.\n\n"
            "Vorgehen:\n"
            "1. Lies den Vorgang mit lesen (typ=\"vorgang\": Kunde, Anlage, Leistungstyp, bisheriger Verlauf).\n"
            "2. Hole mit auflisten (typ=\"vorlage\", filter {vorgang_id}) die für diesen Vorgang verfügbaren Vorlagen und "
            "wähle die passende (bei Zweifel frage nach). Lies sie mit lesen (typ=\"vorlage\").\n"
            "3. Frage den Nutzer nach den Messwerten und Befunden, falls er sie noch nicht genannt hat, und erfinde "
            "nie Werte.\n"
            "4. Lege den Entwurf mit protokoll_entwurf an. Fotos, Unterschriften und GPS kannst du nicht "
            "eintragen.\n"
            "5. Sage dem Nutzer, was noch fehlt (noch_fehlende_pflichtfelder) und dass er das Protokoll in der "
            "FieldVibe-App prüfen, ergänzen, unterschreiben lassen und abschließen muss."
        )

    @mcp.prompt(
        name="monatsbericht",
        title="Monatsbericht",
        description="Erstellt einen Monatsbericht über Vorgänge und Arbeitszeit als Markdown.",
    )
    def monatsbericht(
        monat: Annotated[str, Field(description="Monat im Format JJJJ-MM, z. B. 2026-10")],
        team: Annotated[str, Field(description="Optional: Team oder Techniker (Name oder ID), sonst alle.")] = "",
    ) -> str:
        wer = f" für {team}" if team.strip() else ""
        return (
            f"Erstelle einen Monatsbericht{wer} für {monat} als Markdown.\n\n"
            "Hole die Zahlen mit den Tools, rechne nichts aus dem Kopf:\n"
            "- kennzahlen_vorgaenge (von/bis = erster/letzter Tag des Monats): offene und abgeschlossene Vorgänge, "
            "durchschnittliche Durchlaufzeit.\n"
            "- auswertung: Vorgänge je Leistungstyp und je Techniker (anzahl_abgeschlossen), Arbeitsstunden je "
            "Techniker (arbeitszeit_stunden), bei Rechten auch Umsatz (rechnungen, umsatz_netto je Kunde).\n"
            "Fehlt ein Recht, lasse den Abschnitt weg und sage das kurz.\n\n"
            "Gliederung: Überblick (3-4 Sätze), Kennzahlen-Tabelle, Auffälligkeiten (Vergleich zum Vormonat, falls "
            "abrufbar), offene Punkte. Nenne Zeitraum und Datenquelle (FieldVibe) am Anfang."
        )
