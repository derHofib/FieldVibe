import { Ringpuffer } from "./ringpuffer";
import { schwaerzeText, STANDARD_CONFIG, type SchwaerzConfig } from "./schwaerzen";
import type { KonsolenEintrag } from "./typen";

export interface KonsoleOptionen {
  puffer: Ringpuffer<KonsolenEintrag>;
  konsoleLog?: boolean;
  schwaerz?: SchwaerzConfig;
}

const MAX_NACHRICHT = 2000;
const MAX_STACK = 4000;

type Level = "error" | "warn" | "log";

let deinstallieren: (() => void) | null = null;

function kuerze(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max)}[... gekuerzt]` : text;
}

function sichereJson(wert: object): string {
  // Ancestor-Tracking waere exakter, aber ein WeakSet haelt die Kosten pro Aufruf niedrig;
  // mehrfach referenzierte Objekte erscheinen dann als "[zirkulaer]" -- fuer Diagnose ausreichend.
  const gesehen = new WeakSet<object>();
  try {
    return (
      JSON.stringify(wert, (_k, v: unknown) => {
        if (typeof v === "bigint") return v.toString();
        if (typeof v === "function") return "[Function]";
        if (typeof Node !== "undefined" && v instanceof Node) return `<${v.nodeName.toLowerCase()}>`;
        if (v instanceof Error) return { name: v.name, message: v.message, stack: v.stack };
        if (typeof v === "object" && v !== null) {
          if (gesehen.has(v)) return "[zirkulaer]";
          gesehen.add(v);
        }
        return v;
      }) ?? String(wert)
    );
  } catch {
    return "[nicht serialisierbar]";
  }
}

export function serialisiereArgument(arg: unknown, cfg: SchwaerzConfig): { text: string; stack?: string } {
  if (arg instanceof Error) {
    return {
      text: schwaerzeText(`${arg.name}: ${arg.message}`, cfg),
      stack: arg.stack ? kuerze(schwaerzeText(arg.stack, cfg), MAX_STACK) : undefined,
    };
  }
  if (typeof arg === "string") return { text: schwaerzeText(arg, cfg) };
  if (typeof arg === "function") return { text: "[Function]" };
  if (typeof arg === "object" && arg !== null) return { text: schwaerzeText(sichereJson(arg), cfg) };
  return { text: String(arg) };
}

export function installKonsole(opt: KonsoleOptionen): void {
  if (deinstallieren) return;
  const cfg = opt.schwaerz ?? STANDARD_CONFIG;
  const levels: Level[] = opt.konsoleLog === false ? ["error", "warn"] : ["error", "warn", "log"];
  const originale = new Map<Level, (...a: unknown[]) => void>();
  let inErfassung = false;

  const eintragen = (level: Level, nachricht: string, stack?: string) => {
    const e: KonsolenEintrag = { zeit: new Date().toISOString(), level, nachricht: kuerze(nachricht, MAX_NACHRICHT) };
    if (stack) e.stack = stack;
    opt.puffer.push(e);
  };

  for (const level of levels) {
    const orig = console[level].bind(console) as (...a: unknown[]) => void;
    originale.set(level, console[level] as (...a: unknown[]) => void);
    console[level] = (...args: unknown[]) => {
      // Reentranz-Schutz: Fehler in der Erfassung duerfen sich nicht ueber console selbst aufschaukeln.
      if (!inErfassung) {
        inErfassung = true;
        try {
          const teile = args.map((a) => serialisiereArgument(a, cfg));
          eintragen(level, teile.map((t) => t.text).join(" "), teile.find((t) => t.stack)?.stack);
        } catch {
          // ignorieren
        } finally {
          inErfassung = false;
        }
      }
      orig(...args);
    };
  }

  const onError = (ev: ErrorEvent) => {
    try {
      const fehler = ev.error as unknown;
      const stack = fehler instanceof Error && fehler.stack ? kuerze(schwaerzeText(fehler.stack, cfg), MAX_STACK) : undefined;
      const ort = ev.filename ? ` (${ev.filename}:${ev.lineno}:${ev.colno})` : "";
      eintragen("error", schwaerzeText(`${ev.message}${ort}`, cfg), stack);
    } catch {
      // ignorieren
    }
  };
  const onRejection = (ev: PromiseRejectionEvent) => {
    try {
      const t = serialisiereArgument(ev.reason, cfg);
      eintragen("error", `Unhandled Promise Rejection: ${t.text}`, t.stack);
    } catch {
      // ignorieren
    }
  };
  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onRejection);

  deinstallieren = () => {
    for (const [level, orig] of originale) console[level] = orig;
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onRejection);
  };
}

export function uninstallKonsole(): void {
  deinstallieren?.();
  deinstallieren = null;
}
