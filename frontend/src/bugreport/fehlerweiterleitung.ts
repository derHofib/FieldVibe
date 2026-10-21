// Automatische Fehlermeldung an einen Sentry-kompatiblen Dienst (selbst gehostetes
// GlitchTip oder EU-Sentry). Bewusst ein schlanker Eigenbau statt @sentry/browser:
// keine neue Abhaengigkeit, kein Session-Replay, keine Breadcrumbs, kein Cookie- oder
// Header-Zugriff -- gesendet werden nur Fehlertyp, geschwaerzte Meldung/Stack, Release,
// Umgebung und die Routen-Vorlage der Seite. Ohne DSN wird nichts installiert.
//
// Ergaenzt den manuellen In-App-Fehlerbericht (index.ts): der erfasst Kontext auf Wunsch
// des Nutzers, dies hier meldet unbehandelte Fehler ohne Zutun, aber PII-frei.

import { schwaerzeText, STANDARD_CONFIG, type SchwaerzConfig } from "./schwaerzen";

export interface WeiterleitungConfig {
  dsn: string;
  release: string;
  environment: string;
  // Anteil der Fehler, die gesendet werden (0..1).
  sampleRate?: number;
  schwaerz?: SchwaerzConfig;
  // Fuer Tests.
  fetchFn?: typeof fetch;
  jetzt?: () => number;
}

const MAX_EVENTS_PRO_FENSTER = 10;
const FENSTER_MS = 5 * 60 * 1000;
const MAX_MELDUNG = 1000;
const MAX_STACK = 4000;
// Offline in der Feld-App ist Normalbetrieb, kein Fehler. ResizeObserver-Meldungen sind
// browserseitiges Rauschen.
const IGNORIEREN = [
  /failed to fetch/i,
  /networkerror/i,
  /load failed/i,
  /network request failed/i,
  /resizeobserver loop/i,
  /^script error\.?$/i,
];

interface DsnTeile {
  url: string;
  schluessel: string;
}

export function parseDsn(dsn: string): DsnTeile | null {
  try {
    const u = new URL(dsn);
    const projekt = u.pathname.replace(/^\/+|\/+$/g, "");
    if (!u.username || !projekt || !/^https?:$/.test(u.protocol)) return null;
    return { url: `${u.protocol}//${u.host}/api/${projekt}/envelope/`, schluessel: u.username };
  } catch {
    return null;
  }
}

// IDs und Nummern aus dem Pfad nehmen: Pfadsegmente koennen Kunden-/Vorgangs-IDs oder
// Tokens enthalten. Query und Fragment werden nie uebernommen.
export function normalisierePfad(pfad: string): string {
  return pfad
    .split("?")[0]
    .split("#")[0]
    .replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi, ":id")
    .replace(/\/[A-Za-z0-9_-]{24,}(?=\/|$)/g, "/:token")
    .replace(/\d{3,}/g, ":n");
}

function kuerze(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max)}[... gekuerzt]` : text;
}

function eventId(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

let aufraeumen: (() => void) | null = null;

export function installFehlerweiterleitung(cfg: WeiterleitungConfig): boolean {
  if (aufraeumen) return true;
  const dsn = parseDsn(cfg.dsn);
  if (!dsn) return false;

  const schwaerz = cfg.schwaerz ?? STANDARD_CONFIG;
  const senden = cfg.fetchFn ?? ((...a: Parameters<typeof fetch>) => fetch(...a));
  const jetzt = cfg.jetzt ?? (() => Date.now());
  const sampleRate = cfg.sampleRate ?? 1;
  const gesendet = new Set<string>();
  let fensterStart = jetzt();
  let imFenster = 0;

  const melde = (typ: string, wert: string, stack?: string) => {
    const meldung = kuerze(schwaerzeText(wert, schwaerz), MAX_MELDUNG);
    if (IGNORIEREN.some((r) => r.test(meldung))) return;
    if (sampleRate < 1 && Math.random() >= sampleRate) return;

    const t = jetzt();
    if (t - fensterStart > FENSTER_MS) {
      fensterStart = t;
      imFenster = 0;
      gesendet.clear();
    }
    // Dedupe + Drosselung: eine Render-Schleife darf den Dienst nicht fluten.
    const schluessel = `${typ}|${meldung}`;
    if (gesendet.has(schluessel) || imFenster >= MAX_EVENTS_PRO_FENSTER) return;
    gesendet.add(schluessel);
    imFenster += 1;

    const id = eventId();
    const event = {
      event_id: id,
      timestamp: t / 1000,
      platform: "javascript",
      level: "error",
      release: cfg.release,
      environment: cfg.environment,
      exception: { values: [{ type: typ, value: meldung }] },
      tags: { route: normalisierePfad(window.location.pathname) },
      request: { url: `${window.location.origin}${normalisierePfad(window.location.pathname)}` },
      extra: stack ? { stack: kuerze(schwaerzeText(stack, schwaerz), MAX_STACK) } : undefined,
    };
    const kopf = JSON.stringify({ event_id: id, sent_at: new Date(t).toISOString() });
    const body = `${kopf}\n${JSON.stringify({ type: "event" })}\n${JSON.stringify(event)}`;
    // text/plain: einfacher CORS-Request ohne Preflight (wie das offizielle SDK). Fehler beim
    // Senden werden verschluckt -- die Fehlermeldung darf nie selbst einen Fehler ausloesen.
    try {
      void senden(`${dsn.url}?sentry_key=${encodeURIComponent(dsn.schluessel)}&sentry_version=7`, {
        method: "POST",
        body,
        headers: { "Content-Type": "text/plain;charset=UTF-8" },
        keepalive: true,
        credentials: "omit",
        referrerPolicy: "origin",
      }).catch(() => undefined);
    } catch {
      // ignorieren
    }
  };

  const onError = (ev: ErrorEvent) => {
    const fehler = ev.error as unknown;
    if (fehler instanceof Error) melde(fehler.name || "Error", fehler.message, fehler.stack);
    else melde("Error", ev.message || "Unbekannter Fehler");
  };
  const onRejection = (ev: PromiseRejectionEvent) => {
    const grund = ev.reason as unknown;
    if (grund instanceof Error) melde(grund.name || "Error", `Unhandled rejection: ${grund.message}`, grund.stack);
    else melde("UnhandledRejection", String(grund));
  };
  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onRejection);
  aufraeumen = () => {
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onRejection);
  };
  return true;
}

export function beendeFehlerweiterleitung(): void {
  aufraeumen?.();
  aufraeumen = null;
}
