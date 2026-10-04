import type { FehlerberichtKontext, Kategorie } from "../index";

export type Schweregrad = "niedrig" | "mittel" | "hoch" | "blockierend";

export const KATEGORIEN: { key: Kategorie; label: string }[] = [
  { key: "netzwerk", label: "Netzwerk" },
  { key: "konsole", label: "Konsole" },
  { key: "breadcrumbs", label: "Klickpfad" },
  { key: "umgebung", label: "Umgebung" },
  { key: "sitzung", label: "Sitzung" },
  { key: "app_state", label: "App-Zustand" },
];

export interface FormularWerte {
  titel: string;
  beschreibung: string;
  erwartet: string;
  schritte: string;
  schweregrad: Schweregrad;
}

export interface ScreenshotDateien {
  original: Blob;
  annotiert: Blob;
}

export function filtereKontext(kontext: FehlerberichtKontext, auswahl: ReadonlySet<Kategorie>): FehlerberichtKontext {
  const ergebnis: FehlerberichtKontext = {};
  for (const { key } of KATEGORIEN) {
    if (auswahl.has(key) && kontext[key] !== undefined) (ergebnis as Record<string, unknown>)[key] = kontext[key];
  }
  return ergebnis;
}

export function baueFormular(args: {
  werte: FormularWerte;
  kontext: FehlerberichtKontext;
  auswahl: ReadonlySet<Kategorie>;
  screenshot: ScreenshotDateien | null;
  route?: string;
  appVersion?: string;
  commitSha?: string;
}): FormData {
  const { werte, screenshot } = args;
  const nurGefuellt = (s: string) => (s.trim() ? s.trim() : undefined);
  const payload = {
    titel: werte.titel.trim(),
    beschreibung: werte.beschreibung.trim(),
    erwartet: nurGefuellt(werte.erwartet),
    schritte: nurGefuellt(werte.schritte),
    schweregrad: werte.schweregrad,
    kontext: filtereKontext(args.kontext, args.auswahl),
    route: args.route,
    app_version: args.appVersion,
    commit_sha: args.commitSha,
  };
  const fd = new FormData();
  fd.append("payload", JSON.stringify(payload));
  if (screenshot) {
    fd.append("screenshot_original", screenshot.original, "original.png");
    fd.append("screenshot_annotiert", screenshot.annotiert, "annotiert.png");
  }
  return fd;
}

export interface FehlerHinweis {
  status?: number;
  message?: string;
}

// Der ui-Ordner kennt die App-Fehlerklasse nicht; ein HTTP-Status wird per Duck-Typing gelesen.
export function fehlerText(e: unknown): string {
  const status = typeof (e as FehlerHinweis | null)?.status === "number" ? (e as FehlerHinweis).status : undefined;
  if (status === 429) return "Zu viele Fehlerberichte in kurzer Zeit. Bitte später noch einmal versuchen.";
  if (status === 413) return "Der Bericht ist zu groß. Bitte Screenshot oder einzelne technische Daten abwählen.";
  if (status === undefined) {
    return "Keine Verbindung zum Server. Der Bericht wurde nicht gesendet – bitte Verbindung prüfen und erneut versuchen (ein Offline-Versand ist nicht möglich).";
  }
  const meldung = (e as FehlerHinweis).message;
  return `Senden fehlgeschlagen${meldung ? `: ${meldung}` : ` (Status ${status})`}.`;
}
