// Zentrale Redaction-Pipeline. Reine Funktionen: die Konfiguration kommt immer
// als Argument, damit Erfassung und Snapshot dieselben Regeln nutzen.

export const ENTFERNT = "[entfernt]";

export const HEADER_DENYLIST = [
  "authorization",
  "cookie",
  "set-cookie",
  "proxy-authorization",
  "x-api-key",
  "x-auth-token",
  "x-csrf-token",
];

export const SCHLUESSEL_DENYLIST = [
  "password",
  "passwort",
  "kennwort",
  "token",
  "secret",
  "api_key",
  "apikey",
  "iban",
  "authorization",
  "cookie",
  "pin",
  "credential",
];

export interface SchwaerzConfig {
  denylist: string[];
  maskiereEmail: boolean;
  maskiereIban: boolean;
  maskiereTelefon: boolean;
  // Vorkompiliert, weil die Regex bei jedem Body/jeder Konsolenzeile laeuft; bewusst ohne
  // fuehrendes Wortzeichen-Praefix (quadratisches Backtracking bei langen Woertern).
  kvRegex: RegExp;
}

export interface SchwaerzOptionen {
  zusatzDenylist?: string[];
  maskiereEmail?: boolean;
  maskiereIban?: boolean;
  maskiereTelefon?: boolean;
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function erstelleSchwaerzConfig(opt: SchwaerzOptionen = {}): SchwaerzConfig {
  const denylist = [...SCHLUESSEL_DENYLIST, ...(opt.zusatzDenylist ?? [])]
    .map((s) => s.toLowerCase())
    .filter((s) => s.length > 0);
  const namen = denylist.map(escapeRegex).join("|");
  return {
    denylist,
    maskiereEmail: opt.maskiereEmail ?? true,
    maskiereIban: opt.maskiereIban ?? true,
    maskiereTelefon: opt.maskiereTelefon ?? true,
    kvRegex: new RegExp(
      `((?:${namen})[\\w.-]*)(["']?\\s*[:=]\\s*)("[^"]*"|'[^']*'|[^\\s&,;"']+)`,
      "gi",
    ),
  };
}

export const STANDARD_CONFIG: SchwaerzConfig = erstelleSchwaerzConfig();

const JWT_REGEX = /eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*/g;
const BEARER_REGEX = /\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}/gi;
const EMAIL_REGEX = /[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}/g;
const IBAN_REGEX = /\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b/g;
// Nur Nummern mit fuehrender 0/00/+ -- sonst wuerden ISO-Daten, IDs und
// Millisekunden-Zeitstempel im Freitext faelschlich maskiert.
const TELEFON_REGEX = /(?<![\w.+-])(?:\+|00|0)\d[\d\s/()-]{6,}\d(?![\w])/g;

// Gestufte Obergrenzen: schuetzen vor Endlosrekursion bzw. teurem Parsen.
const MAX_TIEFE = 8;
const MAX_JSON_PARSE = 200_000;

export function istDenylistSchluessel(schluessel: string, cfg: SchwaerzConfig): boolean {
  const klein = schluessel.toLowerCase();
  return cfg.denylist.some((d) => klein.includes(d));
}

export function maskiereMuster(text: string, cfg: SchwaerzConfig, mitTelefon = cfg.maskiereTelefon): string {
  let t = text.replace(JWT_REGEX, ENTFERNT).replace(BEARER_REGEX, `$1 ${ENTFERNT}`);
  if (cfg.maskiereIban) t = t.replace(IBAN_REGEX, "[iban]");
  if (cfg.maskiereEmail) t = t.replace(EMAIL_REGEX, "[email]");
  if (mitTelefon) t = t.replace(TELEFON_REGEX, "[telefon]");
  return t;
}

export function schwaerzeText(text: string, cfg: SchwaerzConfig = STANDARD_CONFIG): string {
  const t = text.trim();
  if ((t.startsWith("{") || t.startsWith("[")) && t.length <= MAX_JSON_PARSE) {
    try {
      return JSON.stringify(schwaerzeWert(JSON.parse(t), cfg));
    } catch {
      // Kein gueltiges JSON -> Regex-Pfad.
    }
  }
  // Bearer zuerst, sonst frisst die Schluessel-Regex nur das Wort "Bearer" und laesst das Token stehen.
  return maskiereMuster(text.replace(BEARER_REGEX, `$1 ${ENTFERNT}`).replace(cfg.kvRegex, `$1$2${ENTFERNT}`), cfg);
}

export function schwaerzeWert(
  wert: unknown,
  cfg: SchwaerzConfig = STANDARD_CONFIG,
  tiefe = 0,
  vorfahren: WeakSet<object> = new WeakSet(),
): unknown {
  if (typeof wert === "string") return schwaerzeText(wert, cfg);
  if (wert === null || wert === undefined) return wert;
  if (typeof wert === "bigint") return wert.toString();
  if (typeof wert === "function") return "[Function]";
  if (typeof wert === "symbol") return wert.toString();
  if (typeof wert !== "object") return wert;
  if (tiefe >= MAX_TIEFE) return "[zu tief]";
  if (vorfahren.has(wert)) return "[zirkulaer]";
  if (wert instanceof Date) return Number.isNaN(wert.getTime()) ? null : wert.toISOString();

  vorfahren.add(wert);
  try {
    if (wert instanceof Error) {
      return {
        name: wert.name,
        message: schwaerzeText(wert.message, cfg),
        stack: wert.stack ? schwaerzeText(wert.stack, cfg) : undefined,
      };
    }
    if (Array.isArray(wert)) {
      return wert.map((v) => schwaerzeWert(v, cfg, tiefe + 1, vorfahren));
    }
    const ergebnis: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(wert)) {
      ergebnis[k] = istDenylistSchluessel(k, cfg) ? ENTFERNT : schwaerzeWert(v, cfg, tiefe + 1, vorfahren);
    }
    return ergebnis;
  } finally {
    vorfahren.delete(wert);
  }
}

export function schwaerzeHeaders(
  headers: Record<string, string>,
  cfg: SchwaerzConfig = STANDARD_CONFIG,
): Record<string, string> {
  const ergebnis: Record<string, string> = {};
  for (const [name, wert] of Object.entries(headers)) {
    ergebnis[name] = HEADER_DENYLIST.includes(name.toLowerCase())
      ? ENTFERNT
      : maskiereMuster(String(wert), cfg);
  }
  return ergebnis;
}

// Schwaerzt Query-Parameter mit Denylist-Namen; Fragment (#...) wird verworfen,
// weil dort bei OAuth-Flows gern Tokens stehen.
export function schwaerzeUrl(url: string, cfg: SchwaerzConfig = STANDARD_CONFIG): string {
  const ohneFragment = url.split("#")[0];
  const q = ohneFragment.indexOf("?");
  let basis = ohneFragment;
  if (q >= 0) {
    const pfad = ohneFragment.slice(0, q);
    const query = ohneFragment
      .slice(q + 1)
      .split("&")
      .map((teil) => {
        const gleich = teil.indexOf("=");
        const name = gleich >= 0 ? teil.slice(0, gleich) : teil;
        let dekodiert = name;
        try {
          dekodiert = decodeURIComponent(name);
        } catch {
          // Rohen Namen verwenden.
        }
        return name && istDenylistSchluessel(dekodiert, cfg) ? `${name}=${ENTFERNT}` : teil;
      })
      .join("&");
    basis = `${pfad}?${query}`;
  }
  // Telefon-Regex bewusst aus: Pfadsegmente wie /vorgaenge/0123456789 sind IDs.
  return maskiereMuster(basis, cfg, false);
}
