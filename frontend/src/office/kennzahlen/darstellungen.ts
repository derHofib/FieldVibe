import type { Darstellung, KennzahlDef, KennzahlGruppierung } from "../../types/kennzahlen";

export const DARSTELLUNG_LABEL: Record<Darstellung, string> = {
  zahl: "Zahl",
  zahl_verlauf: "Zahl mit Verlauf",
  saeulen: "Säulen",
  linie: "Linie",
  balken: "Balken",
  ring: "Ring",
  tabelle: "Tabelle",
};

export const DARSTELLUNG_REIHENFOLGE: Darstellung[] = [
  "zahl", "zahl_verlauf", "saeulen", "linie", "balken", "ring", "tabelle",
];

/** Diagramm-Darstellungen, für die "Als Tabelle" im Widget-Menü sinnvoll ist. */
export const DIAGRAMM_DARSTELLUNGEN: Darstellung[] = ["saeulen", "linie", "balken", "ring"];

const zeitGruppierungen = (def: KennzahlDef) => def.gruppierungen.filter((g) => g.zeit);
const kategorieGruppierungen = (def: KennzahlDef) => def.gruppierungen.filter((g) => !g.zeit);

/** Welche Darstellungen eine Kennzahl überhaupt zulässt. `gruppierung` = bereits gewählte Aufteilung:
 * "gesamt" sperrt die Tabelle (eine einzelne Zeile ist keine Tabelle); null = "noch offen", dann zählt,
 * was die Kennzahl grundsätzlich anbietet (Einstellungen: erst Darstellung wählen, Aufteilung folgt). */
export function erlaubteDarstellungen(def: KennzahlDef, gruppierung: string | null = null): Darstellung[] {
  const hatZeit = zeitGruppierungen(def).length > 0;
  const hatKategorie = kategorieGruppierungen(def).length > 0;
  const erlaubt: Darstellung[] = ["zahl"];
  if (hatZeit) erlaubt.push("zahl_verlauf");
  if (hatZeit || hatKategorie) erlaubt.push("saeulen");
  if (hatZeit) erlaubt.push("linie");
  if (hatKategorie) erlaubt.push("balken");
  // Anteile an einem Ganzen gibt es nur, wenn sich die Teile aufaddieren (Durchlaufzeit/Quoten: nein).
  if (hatKategorie && def.summierbar) erlaubt.push("ring");
  if (def.gruppierungen.length > 0 && gruppierung !== "gesamt") erlaubt.push("tabelle");
  return erlaubt;
}

export function standardDarstellung(_def: KennzahlDef): Darstellung {
  return "zahl";
}

/** Aufteilungen, die zur Darstellung passen (Auswahl "Aufteilen nach"). Zahl-Darstellungen kennen keine. */
export function gruppierungenFuer(def: KennzahlDef, darstellung: Darstellung): KennzahlGruppierung[] {
  switch (darstellung) {
    case "zahl":
    case "zahl_verlauf":
      return [];
    case "linie":
      return zeitGruppierungen(def);
    case "balken":
    case "ring":
      return kategorieGruppierungen(def);
    case "saeulen":
    case "tabelle":
      return def.gruppierungen;
  }
}

/** Aufteilung nach einem Darstellungswechsel: die bisherige behalten, wenn sie passt, sonst eine sinnvolle
 * Vorgabe (Linie/Säulen bevorzugt "monat", Rangliste/Ring die erste Kategorie). null = keine Aufteilung nötig. */
export function passendeGruppierung(def: KennzahlDef, darstellung: Darstellung, aktuell: string | null): string | null {
  const passend = gruppierungenFuer(def, darstellung);
  if (passend.length === 0) return null;
  if (aktuell && passend.some((g) => g.schluessel === aktuell)) return aktuell;
  const zeit = passend.filter((g) => g.zeit);
  if (darstellung === "linie" || darstellung === "saeulen") {
    return (zeit.find((g) => g.schluessel === "monat") ?? zeit[0] ?? passend[0]).schluessel;
  }
  // Tabelle: lieber eine Kategorie (genaue Werte je Techniker/Kunde) als eine Zeitachse.
  return (passend.find((g) => !g.zeit) ?? passend[0]).schluessel;
}

export type Richtung = "hoeher_besser" | "niedriger_besser" | "neutral";

// Nur Kennzahlen mit klarer Richtung färben die Abweichung; bei "erstellt" oder "offene Forderungen"
// ist mehr weder gut noch schlecht (Farbe wäre eine unbelegte Wertung).
const RICHTUNG: Record<string, Richtung> = {
  "vorgaenge.abgeschlossen": "hoeher_besser",
  "vorgaenge.durchlaufzeit": "niedriger_besser",
  "vorgaenge.ueberfaellig": "niedriger_besser",
  "finanzen.umsatz_netto": "hoeher_besser",
  "finanzen.ueberfaellig": "niedriger_besser",
  "sales.angebotsquote": "hoeher_besser",
  "sales.angebote_angenommen": "hoeher_besser",
};

export function richtungFuer(kennzahl: string): Richtung {
  return RICHTUNG[kennzahl] ?? "neutral";
}
