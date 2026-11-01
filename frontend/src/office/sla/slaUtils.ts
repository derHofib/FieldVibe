export type SlaKalenderArt = "rund_um_die_uhr" | "geschaeftszeiten";
export type SlaFristArt = "reaktion" | "loesung";
export type SlaAktion = "benachrichtigen" | "mail";
export type SlaEmpfaenger = "zugewiesener" | "dispo" | "vorgesetzter" | "admin";

export interface SlaZiel {
  reaktion_min?: number | null;
  loesung_min?: number | null;
}

export interface SlaStufe {
  frist_art: SlaFristArt;
  schwelle_prozent: number;
  aktion: SlaAktion;
  empfaenger: SlaEmpfaenger;
}

export interface SlaRichtlinie {
  id: string;
  name: string;
  beschreibung: string | null;
  aktiv: boolean;
  ist_standard: boolean;
  kalender: SlaKalenderArt;
  geschaeftszeiten: Record<string, string[][]>;
  feiertage_ausnehmen: boolean;
  ziele: Record<string, SlaZiel>;
  prioritaet_regeln: Record<string, number>;
  stufen: SlaStufe[];
}

export type SlaRichtlinieEingabe = Omit<SlaRichtlinie, "id">;

export interface SlaFristAuswertung {
  erfuellt: number;
  verletzt: number;
  offen: number;
  quote_prozent: number | null;
  median_minuten: number | null;
  p90_minuten: number | null;
}

export interface SlaAuswertung {
  vorgaenge: number;
  reaktion: SlaFristAuswertung;
  loesung: SlaFristAuswertung;
}

export const WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

export const NEUE_RICHTLINIE: SlaRichtlinieEingabe = {
  name: "",
  beschreibung: null,
  aktiv: true,
  ist_standard: false,
  kalender: "rund_um_die_uhr",
  geschaeftszeiten: {},
  feiertage_ausnehmen: true,
  ziele: { "3": { reaktion_min: 240, loesung_min: 2880 } },
  prioritaet_regeln: {},
  stufen: [
    { frist_art: "reaktion", schwelle_prozent: 75, aktion: "benachrichtigen", empfaenger: "zugewiesener" },
    { frist_art: "reaktion", schwelle_prozent: 100, aktion: "mail", empfaenger: "dispo" },
  ],
};

/** Ein gemeinsames Zeitfenster für die gewählten Wochentage (Editor kennt bewusst nur diesen Fall). */
export function fensterAus(zeiten: Record<string, string[][]>): { tage: number[]; von: string; bis: string } {
  const tage = Object.entries(zeiten)
    .filter(([, f]) => f.length > 0)
    .map(([t]) => Number(t))
    .sort();
  const erstes = tage.length ? zeiten[String(tage[0])][0] : ["07:00", "17:00"];
  return { tage: tage.length ? tage : [0, 1, 2, 3, 4], von: erstes[0], bis: erstes[1] };
}

export function zeitenAus(tage: number[], von: string, bis: string): Record<string, string[][]> {
  return Object.fromEntries(tage.map((t) => [String(t), [[von, bis]]]));
}

/** Zahlenfeld → Minuten oder undefined; leer oder ungültig gilt als „keine Frist“. */
export function minutenOderLeer(text: string): number | undefined {
  const n = Number.parseInt(text, 10);
  return Number.isFinite(n) && n > 0 ? n : undefined;
}

export function dauerText(minuten: number | null | undefined): string {
  if (minuten == null) return "—";
  if (minuten >= 1440 && minuten % 1440 === 0) return `${minuten / 1440} Tg.`;
  if (minuten >= 60) return `${Math.floor(minuten / 60)} Std. ${minuten % 60 ? `${minuten % 60} Min.` : ""}`.trim();
  return `${minuten} Min.`;
}
