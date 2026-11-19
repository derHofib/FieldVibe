import type { Darstellung, DashboardLayout, DashboardWidget, DashboardZeitraum, WidgetGroesse } from "../../types/kennzahlen";

/** Vier Systemvorlagen: fest im Code statt in der Datenbank, damit neue Widgets in späteren Versionen
 * ohne Datenmigration bei allen ankommen. "Anpassen" legt eine persönliche Kopie an, das Original bleibt. */

export type VorlagenSchluessel = "ueberblick" | "vorgaenge" | "finanzen" | "team";

export interface Vorlage {
  schluessel: VorlagenSchluessel;
  name: string;
  layout: DashboardLayout;
}

// Momentaufnahmen kennen keine Vorperiode -- der Vergleichsschalter ist dort ohnehin ausgeblendet.
const STAND = new Set([
  "vorgaenge.offen",
  "vorgaenge.ueberfaellig",
  "finanzen.offene_forderungen",
  "finanzen.ueberfaellig",
  "finanzen.verbindlichkeiten",
]);

function widgets(praefix: string, zeilen: [string, Darstellung, string | null, WidgetGroesse][]): DashboardWidget[] {
  // Feste ids (Präfix + Position): React-Keys und Auswahl bleiben über Neuladen stabil.
  return zeilen.map(([kennzahl, darstellung, gruppierung, groesse], index) => ({
    id: `${praefix}-${index + 1}`,
    kennzahl,
    darstellung,
    gruppierung,
    groesse,
    titel: null,
    vergleich: !STAND.has(kennzahl),
  }));
}

function vorlage(schluessel: VorlagenSchluessel, name: string, zeitraum: DashboardZeitraum, inhalt: DashboardWidget[]): Vorlage {
  return { schluessel, name, layout: { zeitraum, widgets: inhalt } };
}

export const VORLAGEN: Vorlage[] = [
  vorlage("ueberblick", "Überblick", "monat", widgets("ueberblick", [
    ["vorgaenge.offen", "zahl", null, "s"],
    ["vorgaenge.ueberfaellig", "zahl", null, "s"],
    ["finanzen.umsatz_netto", "zahl", null, "s"],
    ["finanzen.offene_forderungen", "zahl", null, "s"],
    ["vorgaenge.erstellt", "saeulen", "woche", "l"],
    // Umsatz kennt nur Monate als Zeitachse; im Monats-Zeitraum waere das eine einzige Saeule.
    ["finanzen.umsatz_netto", "balken", "kunde", "l"],
    ["vorgaenge.offen", "ring", "status", "l"],
    ["vorgaenge.abgeschlossen", "balken", "techniker", "l"],
    ["sales.angebotsquote", "zahl", null, "s"],
    ["telefonate.anzahl", "zahl", null, "s"],
    ["vorgaenge.durchlaufzeit", "zahl", null, "s"],
    ["finanzen.ueberfaellig", "zahl", null, "s"],
  ])),
  vorlage("vorgaenge", "Vorgänge", "monat", widgets("vorgaenge", [
    ["vorgaenge.erstellt", "zahl", null, "s"],
    ["vorgaenge.abgeschlossen", "zahl", null, "s"],
    ["vorgaenge.durchlaufzeit", "zahl", null, "s"],
    ["vorgaenge.ueberfaellig", "zahl", null, "s"],
    ["vorgaenge.erstellt", "linie", "woche", "xl"],
    ["vorgaenge.abgeschlossen", "balken", "techniker", "l"],
    ["vorgaenge.erstellt", "ring", "leistungstyp", "l"],
    ["vorgaenge.offen", "balken", "status", "xl"],
  ])),
  vorlage("finanzen", "Finanzen", "jahr", widgets("finanzen", [
    ["finanzen.umsatz_netto", "zahl", null, "s"],
    ["finanzen.offene_forderungen", "zahl", null, "s"],
    ["finanzen.ueberfaellig", "zahl", null, "s"],
    ["finanzen.verbindlichkeiten", "zahl", null, "s"],
    ["finanzen.umsatz_netto", "saeulen", "monat", "xl"],
    ["finanzen.offene_forderungen", "balken", "alter", "l"],
    ["finanzen.umsatz_netto", "tabelle", "kunde", "l"],
    ["sales.angebote_versendet", "zahl", null, "m"],
    ["sales.angebote_angenommen", "zahl", null, "m"],
    ["sales.angebotsquote", "zahl_verlauf", null, "m"],
  ])),
  // Die Arbeitszeit-Widgets des Team-Dashboards folgen in Etappe C (anderes Konzept).
  vorlage("team", "Team", "monat", widgets("team", [
    ["vorgaenge.offen", "balken", "techniker", "l"],
    ["vorgaenge.abgeschlossen", "balken", "techniker", "l"],
    ["telefonate.dauer", "balken", "techniker", "l"],
    ["telefonate.anzahl", "saeulen", "woche", "l"],
  ])),
];

/** Vorlage auf den Katalog des Nutzers zuschneiden: Widgets ohne sichtbare Kennzahl entfallen,
 * bleibt nichts übrig, gibt es keinen Tab (null). Gibt eine Kopie zurück, die Vorlage bleibt unverändert. */
export function vorlageFuerKatalog(v: Vorlage, katalogSchluessel: ReadonlySet<string>): Vorlage | null {
  const sichtbar = v.layout.widgets.filter((w) => katalogSchluessel.has(w.kennzahl)).map((w) => ({ ...w }));
  if (sichtbar.length === 0) return null;
  return { ...v, layout: { ...v.layout, widgets: sichtbar } };
}
