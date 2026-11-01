import { installBreadcrumbs, uninstallBreadcrumbs } from "./breadcrumbs";
import { installKonsole, uninstallKonsole } from "./konsole";
import { installNetzwerk, uninstallNetzwerk } from "./netzwerk";
import { Ringpuffer } from "./ringpuffer";
import {
  erstelleSchwaerzConfig,
  maskiereMuster,
  schwaerzeHeaders,
  schwaerzeText,
  schwaerzeUrl,
  schwaerzeWert,
  type SchwaerzConfig,
} from "./schwaerzen";
import type {
  Breadcrumb,
  FehlerberichtKontext,
  Kategorie,
  KonsolenEintrag,
  NetzwerkEintrag,
  Sitzung,
} from "./typen";
import { erfasseUmgebung } from "./umgebung";

export type { FehlerberichtKontext, Kategorie, Sitzung } from "./typen";

export interface FehlerberichtConfig {
  appVersion: string;
  commitSha: string;
  getSitzung: () => Sitzung | null;
  maxNetzwerk?: number;
  maxKonsole?: number;
  maxBreadcrumbs?: number;
  maxBodyBytes?: number;
  konsoleLog?: boolean;
  ignoreUrls?: (string | RegExp)[];
  zusatzDenylist?: string[];
  maskiereEmail?: boolean;
  maskiereIban?: boolean;
  maskiereTelefon?: boolean;
}

interface Zustand {
  config: FehlerberichtConfig;
  schwaerz: SchwaerzConfig;
  netzwerk: Ringpuffer<NetzwerkEintrag>;
  konsole: Ringpuffer<KonsolenEintrag>;
  breadcrumbs: Ringpuffer<Breadcrumb>;
}

const ALLE: Kategorie[] = ["netzwerk", "konsole", "breadcrumbs", "umgebung", "sitzung", "app_state"];
const MAX_STATE_ZEICHEN = 10_000;

let zustand: Zustand | null = null;
const debugStates = new Map<string, () => unknown>();

export function initFehlerbericht(config: FehlerberichtConfig): void {
  // Erneutes init (z. B. Vite-HMR) soll Wrapper nicht stapeln.
  beendeFehlerbericht();
  const schwaerz = erstelleSchwaerzConfig({
    zusatzDenylist: config.zusatzDenylist,
    maskiereEmail: config.maskiereEmail,
    maskiereIban: config.maskiereIban,
    maskiereTelefon: config.maskiereTelefon,
  });
  const netzwerk = new Ringpuffer<NetzwerkEintrag>(config.maxNetzwerk ?? 50);
  const konsole = new Ringpuffer<KonsolenEintrag>(config.maxKonsole ?? 100);
  const breadcrumbs = new Ringpuffer<Breadcrumb>(config.maxBreadcrumbs ?? 100);
  zustand = { config, schwaerz, netzwerk, konsole, breadcrumbs };

  installNetzwerk({ puffer: netzwerk, maxBodyBytes: config.maxBodyBytes, ignoreUrls: config.ignoreUrls, schwaerz });
  installKonsole({ puffer: konsole, konsoleLog: config.konsoleLog, schwaerz });
  installBreadcrumbs({ puffer: breadcrumbs, schwaerz });
}

// Fuer Tests und HMR: entfernt alle Patches und verwirft die Puffer.
export function beendeFehlerbericht(): void {
  uninstallNetzwerk();
  uninstallKonsole();
  uninstallBreadcrumbs();
  zustand = null;
}

export function registriereDebugState(name: string, fn: () => unknown): () => void {
  debugStates.set(name, fn);
  return () => {
    // Nur entfernen, wenn der Name nicht inzwischen neu belegt wurde.
    if (debugStates.get(name) === fn) debugStates.delete(name);
  };
}

function leseDebugStates(schwaerz: SchwaerzConfig): Record<string, unknown> {
  const ergebnis: Record<string, unknown> = {};
  for (const [name, fn] of debugStates) {
    try {
      const wert = schwaerzeWert(fn(), schwaerz);
      const json = JSON.stringify(wert) ?? "";
      ergebnis[name] = json.length > MAX_STATE_ZEICHEN ? `${json.slice(0, MAX_STATE_ZEICHEN)}[... gekuerzt]` : wert;
    } catch (e) {
      ergebnis[name] = `[Fehler beim Auslesen: ${e instanceof Error ? e.message : String(e)}]`;
    }
  }
  return ergebnis;
}

function schwaerzeNetzwerkEintrag(e: NetzwerkEintrag, cfg: SchwaerzConfig): NetzwerkEintrag {
  const kopie: NetzwerkEintrag = { ...e, url: schwaerzeUrl(e.url, cfg) };
  if (e.request_headers) kopie.request_headers = schwaerzeHeaders(e.request_headers, cfg);
  if (e.response_headers) kopie.response_headers = schwaerzeHeaders(e.response_headers, cfg);
  if (e.request_body !== undefined) kopie.request_body = schwaerzeText(e.request_body, cfg);
  if (e.response_body !== undefined) kopie.response_body = schwaerzeText(e.response_body, cfg);
  if (e.fehler !== undefined) kopie.fehler = schwaerzeText(e.fehler, cfg);
  return kopie;
}

export function sammleKontext(kategorien: Kategorie[] = ALLE): FehlerberichtKontext {
  const kontext: FehlerberichtKontext = {};
  const z = zustand;
  if (!z) return kontext;
  const cfg = z.schwaerz;
  const gewaehlt = new Set(kategorien);

  if (gewaehlt.has("netzwerk")) kontext.netzwerk = z.netzwerk.toArray().map((e) => schwaerzeNetzwerkEintrag(e, cfg));
  if (gewaehlt.has("konsole")) {
    kontext.konsole = z.konsole.toArray().map((e) => ({
      ...e,
      nachricht: schwaerzeText(e.nachricht, cfg),
      ...(e.stack ? { stack: schwaerzeText(e.stack, cfg) } : {}),
    }));
  }
  if (gewaehlt.has("breadcrumbs")) {
    kontext.breadcrumbs = z.breadcrumbs.toArray().map((b) => ({
      ...b,
      ziel: maskiereMuster(b.ziel, cfg, false),
      ...(b.text ? { text: schwaerzeText(b.text, cfg) } : {}),
    }));
  }
  if (gewaehlt.has("umgebung")) {
    kontext.umgebung = erfasseUmgebung({ appVersion: z.config.appVersion, commitSha: z.config.commitSha, schwaerz: cfg });
  }
  if (gewaehlt.has("sitzung")) {
    let sitzung: Sitzung | null = null;
    try {
      sitzung = z.config.getSitzung();
    } catch {
      sitzung = null;
    }
    // IDs bewusst nicht durch die Text-Maskierung: eine UUID mit fuehrender 0 wuerde als Telefonnummer erkannt.
    const roh = sitzung ?? {};
    kontext.sitzung = {
      ...(roh.user_id ? { user_id: String(roh.user_id).slice(0, 100) } : {}),
      ...(roh.mandant_id ? { mandant_id: String(roh.mandant_id).slice(0, 100) } : {}),
      ...(roh.rolle ? { rolle: String(roh.rolle).slice(0, 100) } : {}),
      ...(Array.isArray(roh.flags) ? { flags: roh.flags.map((f) => schwaerzeText(String(f), cfg)) } : {}),
    };
  }
  if (gewaehlt.has("app_state")) kontext.app_state = leseDebugStates(cfg);
  return kontext;
}
