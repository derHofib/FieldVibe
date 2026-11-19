// Laufende Anruf-Uhr: rein lokal im Gerät (kein Server-Timer), übersteht aber
// einen Neuladen über localStorage. Reine Funktionen mit austauschbarem
// Speicher, damit die Logik ohne Browser testbar bleibt.

export interface AnrufUhr {
  /** Startzeitpunkt in ms seit Epoche. */
  start: number;
  kundeId: string | null;
  vorgangId: string | null;
  ansprechpartnerId: string | null;
  partnerName: string | null;
  partnerNummer: string | null;
}

export type UhrSpeicher = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export const UHR_SCHLUESSEL = "fieldvibe-anruf-uhr";

// Eine vergessene Uhr soll nicht tagelang als "laufendes Gespräch" wiederkehren.
export const UHR_MAX_ALTER_MS = 12 * 60 * 60 * 1000;

function standardSpeicher(): UhrSpeicher | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

export function uhrStarten(
  kontext: Partial<Omit<AnrufUhr, "start">>,
  jetzt: number = Date.now(),
  speicher: UhrSpeicher | null = standardSpeicher(),
): AnrufUhr {
  const uhr: AnrufUhr = {
    start: jetzt,
    kundeId: kontext.kundeId ?? null,
    vorgangId: kontext.vorgangId ?? null,
    ansprechpartnerId: kontext.ansprechpartnerId ?? null,
    partnerName: kontext.partnerName ?? null,
    partnerNummer: kontext.partnerNummer ?? null,
  };
  try {
    speicher?.setItem(UHR_SCHLUESSEL, JSON.stringify(uhr));
  } catch {
    // Ohne Speicher läuft die Uhr trotzdem, nur ein Neuladen verliert sie.
  }
  return uhr;
}

export function uhrLaden(
  jetzt: number = Date.now(),
  speicher: UhrSpeicher | null = standardSpeicher(),
): AnrufUhr | null {
  try {
    const roh = speicher?.getItem(UHR_SCHLUESSEL);
    if (!roh) return null;
    const wert = JSON.parse(roh) as Partial<AnrufUhr>;
    if (typeof wert.start !== "number" || !Number.isFinite(wert.start)) return null;
    if (wert.start > jetzt + 60_000 || jetzt - wert.start > UHR_MAX_ALTER_MS) {
      uhrLoeschen(speicher);
      return null;
    }
    return {
      start: wert.start,
      kundeId: wert.kundeId ?? null,
      vorgangId: wert.vorgangId ?? null,
      ansprechpartnerId: wert.ansprechpartnerId ?? null,
      partnerName: wert.partnerName ?? null,
      partnerNummer: wert.partnerNummer ?? null,
    };
  } catch {
    return null;
  }
}

export function uhrLoeschen(speicher: UhrSpeicher | null = standardSpeicher()): void {
  try {
    speicher?.removeItem(UHR_SCHLUESSEL);
  } catch {
    // siehe uhrStarten
  }
}

/** Verstrichene volle Sekunden; nie negativ, auch wenn die Geräteuhr zurückspringt. */
export function uhrSekunden(uhr: Pick<AnrufUhr, "start">, jetzt: number = Date.now()): number {
  return Math.max(0, Math.floor((jetzt - uhr.start) / 1000));
}

/** mm:ss; über eine Stunde läuft die Minutenzahl weiter (75:03), kein Stundenfeld. */
export function formatUhr(sekunden: number): string {
  const s = Math.max(0, Math.floor(sekunden));
  const min = Math.floor(s / 60);
  return `${String(min).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** Stopp: Dauer in Sekunden (an die API) und der Startzeitpunkt als Beginn des Gesprächs. */
export function uhrStoppen(
  uhr: AnrufUhr,
  jetzt: number = Date.now(),
  speicher: UhrSpeicher | null = standardSpeicher(),
): { dauerSekunden: number; beginn: Date } {
  uhrLoeschen(speicher);
  return { dauerSekunden: uhrSekunden(uhr, jetzt), beginn: new Date(uhr.start) };
}
