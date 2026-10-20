import type {
  DublettenAktion,
  ImportAnalyse,
  ImportDublettenArt,
  ImportKonfiguration,
  ImportModus,
  ImportVorschlag,
  ImportZeile,
  ImportZusammenfassung,
  ZeilenStatus,
} from "./typen";

export type Schritt = 1 | 2 | 3 | 4;

export const SCHRITT_TITEL: Record<Schritt, string> = {
  1: "Datei & Typ",
  2: "Zuordnung",
  3: "Probelauf",
  4: "Ergebnis",
};

export const ENTITAET_LABEL = {
  kunden: "Kunden",
  anlagen: "Standorte & Anlagen",
  material: "Material / Artikel",
} as const;

export const AKTION_LABEL: Record<DublettenAktion, string> = {
  ueberspringen: "Überspringen",
  aktualisieren: "Leere Felder aktualisieren",
  anlegen: "Trotzdem anlegen",
};

export const STATUS_LABEL: Record<ZeilenStatus, string> = {
  neu: "Neu",
  warnung: "Warnung",
  dublette: "Dublette",
  fehler: "Fehler",
};

export const LAUF_STATUS_LABEL: Record<string, string> = {
  analysiert: "Analysiert",
  geprueft: "Geprüft",
  abgeschlossen: "Abgeschlossen",
  abgebrochen: "Abgebrochen",
  rueckgaengig: "Rückgängig gemacht",
  abgelaufen: "Verworfen / abgelaufen",
};

export type Mapping = Record<string, number | null>;

/** Aus dem Server-Vorschlag eine Zuordnung machen (Feld -> Spaltenindex). */
export function mappingAusVorschlag(vorschlag: ImportVorschlag[]): Mapping {
  const mapping: Mapping = {};
  for (const v of vorschlag) mapping[v.feld] = v.spalte;
  return mapping;
}

/** Spalte einem Feld zuweisen. Jede Spalte darf nur einem Feld gehoeren: eine
 * zuvor anderweitig belegte Spalte wird dort freigegeben. */
export function spalteZuweisen(mapping: Mapping, feld: string, spalte: number | null): Mapping {
  const neu: Mapping = { ...mapping };
  if (spalte !== null) {
    for (const [k, v] of Object.entries(neu)) if (v === spalte && k !== feld) neu[k] = null;
  }
  neu[feld] = spalte;
  return neu;
}

/** Pflichtgruppen, in denen noch kein Feld zugeordnet ist (je Gruppe genuegt ein Feld). */
export function offenePflichtGruppen(mapping: Mapping, gruppen: string[][]): string[][] {
  return gruppen.filter((gruppe) => !gruppe.some((feld) => mapping[feld] != null));
}

export function pflichtLabel(analyse: ImportAnalyse, gruppe: string[]): string {
  return gruppe.map((key) => analyse.felder.find((f) => f.key === key)?.label ?? key).join(" oder ");
}

export function standardAktionen(arten: ImportDublettenArt[]): Record<string, DublettenAktion> {
  return Object.fromEntries(arten.map((a) => [a.key, a.standard]));
}

export function konfigurationBauen(
  mapping: Mapping,
  modus: ImportModus,
  aktionen: Record<string, DublettenAktion>,
): ImportKonfiguration {
  return { mapping, modus, chargengroesse: 200, dubletten_aktionen: aktionen };
}

export function schrittErreichbar(
  ziel: Schritt,
  zustand: { analyse: ImportAnalyse | null; mappingGueltig: boolean; probelaufErfolgt: boolean; abgeschlossen: boolean },
): boolean {
  if (ziel === 1) return !zustand.abgeschlossen;
  if (ziel === 2) return zustand.analyse !== null && !zustand.abgeschlossen;
  if (ziel === 3) {
    return zustand.analyse !== null && zustand.mappingGueltig && zustand.probelaufErfolgt && !zustand.abgeschlossen;
  }
  return zustand.abgeschlossen;
}

/** Import ausfuehren ist sinnvoll, wenn etwas geschrieben wuerde und -- im Modus
 * "alles oder nichts" -- keine Zeile fehlerhaft ist. */
export function darfAusfuehren(z: ImportZusammenfassung, modus: ImportModus): boolean {
  if (z.anlegen + z.aktualisieren === 0) return false;
  return !(modus === "alles_oder_nichts" && z.fehler > 0);
}

export type ZeilenFilter = ZeilenStatus | "alle";

export function zeilenFiltern(zeilen: ImportZeile[], filter: ZeilenFilter): ImportZeile[] {
  return filter === "alle" ? zeilen : zeilen.filter((z) => z.status === filter);
}

export function statusAnzahl(z: ImportZusammenfassung, status: ZeilenFilter): number {
  return status === "alle" ? z.gesamt : z[status];
}

export function dateigroesseText(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
