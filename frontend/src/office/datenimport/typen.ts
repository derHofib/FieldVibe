export type ImportEntitaet = "kunden" | "anlagen" | "material";
export type ImportModus = "gueltige" | "alles_oder_nichts";
export type DublettenAktion = "ueberspringen" | "aktualisieren" | "anlegen";
export type ZeilenStatus = "neu" | "warnung" | "dublette" | "fehler";

export interface ImportSpalte {
  index: number;
  name: string;
  beispiele: string[];
}

export interface ImportFeld {
  key: string;
  label: string;
  pflicht: boolean;
  gruppe: string | null;
  hinweis: string | null;
}

export interface ImportVorschlag {
  feld: string;
  spalte: number | null;
  sicherheit: "sicher" | "vermutet" | null;
}

export interface ImportDublettenArt {
  key: string;
  label: string;
  aktionen: DublettenAktion[];
  standard: DublettenAktion;
}

export interface ImportAnalyse {
  import_lauf_id: string;
  entitaet: ImportEntitaet;
  dateiname: string;
  format: "csv" | "xlsx";
  trennzeichen: string | null;
  kodierung: string | null;
  blatt: string | null;
  blaetter: string[];
  zeilen_gesamt: number;
  spalten: ImportSpalte[];
  felder: ImportFeld[];
  vorschlag: ImportVorschlag[];
  dubletten_arten: ImportDublettenArt[];
  pflicht_hinweis: string;
  pflicht_gruppen: string[][];
}

export interface ImportKonfiguration {
  mapping: Record<string, number | null>;
  modus: ImportModus;
  chargengroesse: number;
  dubletten_aktionen: Record<string, DublettenAktion>;
}

export interface ImportZeile {
  zeile: number;
  status: ZeilenStatus;
  aktion: "anlegen" | "aktualisieren" | "ueberspringen" | "keine";
  meldungen: string[];
  vorschau: Record<string, string>;
  dublette_art: string | null;
  dublette_von: string | null;
}

export interface ImportZusammenfassung {
  gesamt: number;
  neu: number;
  warnung: number;
  dublette: number;
  fehler: number;
  anlegen: number;
  aktualisieren: number;
  ueberspringen: number;
}

export interface ImportErgebnis {
  import_lauf_id: string;
  status: string;
  zusammenfassung: ImportZusammenfassung;
  zeilen: ImportZeile[];
  zeilen_gekuerzt: boolean;
  abbruch: string | null;
  fehlerbericht_verfuegbar: boolean;
}

export interface ImportRueckgaengigErgebnis {
  zurueckgesetzt: Record<string, number>;
  uebersprungen_gesamt: number;
  bereits_im_papierkorb: number;
  aktualisierte_nicht_zurueckgesetzt: number;
}

export interface ImportLauf {
  id: string;
  entitaet: ImportEntitaet;
  dateiname: string;
  sha256: string;
  dateigroesse: number;
  format: string;
  status: string;
  zeilen_gesamt: number;
  zeilen_neu: number;
  zeilen_aktualisiert: number;
  zeilen_uebersprungen: number;
  zeilen_fehler: number;
  zeilen_warnungen: number;
  ergebnis: { rueckgaengig?: ImportRueckgaengigErgebnis } | null;
  created_at: string;
  abgeschlossen_am: string | null;
  kann_rueckgaengig: boolean;
  fehlerbericht_verfuegbar: boolean;
  quelle_verfuegbar: boolean;
}
