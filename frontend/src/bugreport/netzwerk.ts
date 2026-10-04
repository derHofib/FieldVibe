import { Ringpuffer } from "./ringpuffer";
import {
  schwaerzeHeaders,
  schwaerzeText,
  schwaerzeUrl,
  STANDARD_CONFIG,
  type SchwaerzConfig,
} from "./schwaerzen";
import type { NetzwerkEintrag } from "./typen";

export const STANDARD_IGNORE: (string | RegExp)[] = ["/api/fehlerberichte"];

export interface NetzwerkOptionen {
  puffer: Ringpuffer<NetzwerkEintrag>;
  maxBodyBytes?: number;
  ignoreUrls?: (string | RegExp)[];
  schwaerz?: SchwaerzConfig;
}

interface Kontext {
  puffer: Ringpuffer<NetzwerkEintrag>;
  maxBodyBytes: number;
  ignoreUrls: (string | RegExp)[];
  schwaerz: SchwaerzConfig;
}

let originalFetch: typeof fetch | null = null;
let gepatchtFetch: typeof fetch | null = null;
let originalXhr: {
  open: XMLHttpRequest["open"];
  send: XMLHttpRequest["send"];
  setRequestHeader: XMLHttpRequest["setRequestHeader"];
} | null = null;

function absolut(url: string): string {
  try {
    return new URL(url, globalThis.location?.href).href;
  } catch {
    return url;
  }
}

function wirdIgnoriert(url: string, ctx: Kontext): boolean {
  return ctx.ignoreUrls.some((m) => (typeof m === "string" ? url.includes(m) : m.test(url)));
}

export function kuerzeText(text: string, maxBytes: number): string {
  // Ein Zeichen belegt hoechstens 3 Bytes (UTF-16-Einheit), kurze Texte brauchen keinen Encoder.
  if (text.length * 3 <= maxBytes) return text;
  const bytes = new TextEncoder().encode(text);
  if (bytes.length <= maxBytes) return text;
  const kopf = new TextDecoder().decode(bytes.slice(0, maxBytes));
  return `${kopf}\n[... gekuerzt, ${bytes.length} Bytes insgesamt]`;
}

function bodyAlsText(text: string, ctx: Kontext): string {
  // Erst schwaerzen, dann kuerzen: ein abgeschnittenes JSON liesse sich nicht mehr parsen.
  return kuerzeText(schwaerzeText(text, ctx.schwaerz), ctx.maxBodyBytes);
}

function requestBodyBeschreiben(body: unknown, ctx: Kontext): string | undefined {
  if (body === null || body === undefined) return undefined;
  if (typeof body === "string") return bodyAlsText(body, ctx);
  if (typeof URLSearchParams !== "undefined" && body instanceof URLSearchParams) {
    return bodyAlsText(body.toString(), ctx);
  }
  if (typeof FormData !== "undefined" && body instanceof FormData) return "[FormData]";
  if (typeof Blob !== "undefined" && body instanceof Blob) return `[binär, ${body.size} Bytes]`;
  if (body instanceof ArrayBuffer || ArrayBuffer.isView(body)) {
    return `[binär, ${body.byteLength} Bytes]`;
  }
  return "[Body nicht lesbar]";
}

function headersZuRecord(h: HeadersInit | undefined): Record<string, string> {
  const ergebnis: Record<string, string> = {};
  if (!h) return ergebnis;
  new Headers(h).forEach((wert, name) => {
    ergebnis[name] = wert;
  });
  return ergebnis;
}

function istTextContentType(ct: string | null): boolean {
  if (!ct) return true;
  return /^(text\/|application\/(json|xml|x-www-form-urlencoded|javascript|problem\+json)|.*\+(json|xml))/i.test(ct);
}

async function leseResponseBody(res: Response, ctx: Kontext): Promise<string | undefined> {
  const kopie = res.clone();
  if (!istTextContentType(kopie.headers.get("content-type"))) {
    const groesse = (await kopie.arrayBuffer()).byteLength;
    return `[binär, ${groesse} Bytes]`;
  }
  return bodyAlsText(await kopie.text(), ctx);
}

function fehlerText(err: unknown): string {
  if (err instanceof Error) return `${err.name}: ${err.message}`;
  return String(err);
}

function patchFetch(ctx: Kontext): void {
  const orig = globalThis.fetch;
  if (typeof orig !== "function") return;
  originalFetch = orig;

  const patched = function (this: unknown, input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    let meta: { url: string; methode: string; reqHeaders: Record<string, string>; body: unknown } | null = null;
    const zeit = new Date().toISOString();
    const start = performance.now();
    try {
      const istRequest = typeof Request !== "undefined" && input instanceof Request;
      const rohUrl = istRequest ? input.url : input instanceof URL ? input.href : String(input);
      const url = absolut(rohUrl);
      if (!wirdIgnoriert(url, ctx)) {
        meta = {
          url,
          methode: (init?.method ?? (istRequest ? input.method : "GET")).toUpperCase(),
          reqHeaders: headersZuRecord(init?.headers ?? (istRequest ? input.headers : undefined)),
          // Nur die Referenz merken; gelesen/serialisiert wird erst im Fehlerfall.
          // Bodies eines Request-Objekts bleiben bewusst unerfasst (Clone waere bei jedem Request teuer).
          body: init?.body,
        };
      }
    } catch {
      meta = null;
    }

    // Unveraendert durchreichen: dieselbe Promise geht an den Aufrufer, synchrone Exceptions
    // und Rejections bleiben damit unangetastet.
    const promise = orig.call(globalThis, input, init);
    if (!meta) return promise;
    const m = meta;

    promise.then(
      (res) => {
        try {
          const eintrag: NetzwerkEintrag = {
            zeit,
            methode: m.methode,
            url: schwaerzeUrl(m.url, ctx.schwaerz),
            status: res.status,
            dauer_ms: Math.round(performance.now() - start),
            request_headers: schwaerzeHeaders(m.reqHeaders, ctx.schwaerz),
            response_headers: schwaerzeHeaders(headersZuRecord(res.headers), ctx.schwaerz),
          };
          ctx.puffer.push(eintrag);
          if (res.status >= 400) {
            eintrag.request_body = requestBodyBeschreiben(m.body, ctx);
            leseResponseBody(res, ctx)
              .then((b) => {
                if (b !== undefined) eintrag.response_body = b;
              })
              .catch(() => {});
          }
        } catch {
          // Erfassung darf die App nie beeintraechtigen.
        }
      },
      (err: unknown) => {
        try {
          ctx.puffer.push({
            zeit,
            methode: m.methode,
            url: schwaerzeUrl(m.url, ctx.schwaerz),
            status: 0,
            dauer_ms: Math.round(performance.now() - start),
            fehler: fehlerText(err),
            request_headers: schwaerzeHeaders(m.reqHeaders, ctx.schwaerz),
            request_body: requestBodyBeschreiben(m.body, ctx),
          });
        } catch {
          // s. o.
        }
      },
    );
    return promise;
  };
  gepatchtFetch = patched as typeof fetch;
  globalThis.fetch = gepatchtFetch;
}

interface XhrMeta {
  methode: string;
  url: string;
  headers: Record<string, string>;
}

function parseRohHeader(roh: string): Record<string, string> {
  const ergebnis: Record<string, string> = {};
  for (const zeile of roh.trim().split(/[\r\n]+/)) {
    const i = zeile.indexOf(":");
    if (i > 0) ergebnis[zeile.slice(0, i).trim().toLowerCase()] = zeile.slice(i + 1).trim();
  }
  return ergebnis;
}

function xhrResponseBody(xhr: XMLHttpRequest, ctx: Kontext): string | undefined {
  try {
    if (xhr.responseType === "" || xhr.responseType === "text") return bodyAlsText(xhr.responseText, ctx);
    if (xhr.responseType === "json") return bodyAlsText(JSON.stringify(xhr.response), ctx);
    const r = xhr.response as { byteLength?: number; size?: number } | null;
    return `[binär, ${r?.byteLength ?? r?.size ?? 0} Bytes]`;
  } catch {
    return undefined;
  }
}

function patchXhr(ctx: Kontext): void {
  const Proto = globalThis.XMLHttpRequest?.prototype;
  if (!Proto) return;
  originalXhr = { open: Proto.open, send: Proto.send, setRequestHeader: Proto.setRequestHeader };
  const orig = originalXhr;
  const metas = new WeakMap<XMLHttpRequest, XhrMeta>();

  Proto.open = function (this: XMLHttpRequest, ...args: unknown[]) {
    try {
      metas.set(this, { methode: String(args[0]).toUpperCase(), url: absolut(String(args[1])), headers: {} });
    } catch {
      // ignorieren
    }
    return (orig.open as (...a: unknown[]) => void).apply(this, args);
  } as XMLHttpRequest["open"];

  Proto.setRequestHeader = function (this: XMLHttpRequest, name: string, wert: string) {
    try {
      const m = metas.get(this);
      if (m) m.headers[name.toLowerCase()] = m.headers[name.toLowerCase()] ? `${m.headers[name.toLowerCase()]}, ${wert}` : wert;
    } catch {
      // ignorieren
    }
    return orig.setRequestHeader.call(this, name, wert);
  };

  Proto.send = function (this: XMLHttpRequest, body?: Document | XMLHttpRequestBodyInit | null) {
    try {
      const m = metas.get(this);
      if (m && !wirdIgnoriert(m.url, ctx)) {
        const xhr = this;
        const zeit = new Date().toISOString();
        const start = performance.now();
        let fehler: string | undefined;
        xhr.addEventListener("error", () => (fehler = "Netzwerkfehler"));
        xhr.addEventListener("abort", () => (fehler = "Abgebrochen"));
        xhr.addEventListener("timeout", () => (fehler = "Zeitueberschreitung"));
        xhr.addEventListener("loadend", () => {
          try {
            const eintrag: NetzwerkEintrag = {
              zeit,
              methode: m.methode,
              url: schwaerzeUrl(m.url, ctx.schwaerz),
              status: xhr.status,
              dauer_ms: Math.round(performance.now() - start),
              request_headers: schwaerzeHeaders(m.headers, ctx.schwaerz),
            };
            if (fehler) eintrag.fehler = fehler;
            else eintrag.response_headers = schwaerzeHeaders(parseRohHeader(xhr.getAllResponseHeaders()), ctx.schwaerz);
            if (fehler || xhr.status >= 400) {
              eintrag.request_body = requestBodyBeschreiben(body, ctx);
              if (!fehler) eintrag.response_body = xhrResponseBody(xhr, ctx);
            }
            ctx.puffer.push(eintrag);
          } catch {
            // Erfassung darf die App nie beeintraechtigen.
          }
        });
      }
    } catch {
      // ignorieren
    }
    return orig.send.call(this, body);
  };
}

export function installNetzwerk(opt: NetzwerkOptionen): void {
  // Idempotent: ein zweites install wuerde sonst den Wrapper wrappen und jeden Request doppelt erfassen.
  if (originalFetch || originalXhr) return;
  const ctx: Kontext = {
    puffer: opt.puffer,
    maxBodyBytes: opt.maxBodyBytes ?? 10240,
    ignoreUrls: [...STANDARD_IGNORE, ...(opt.ignoreUrls ?? [])],
    schwaerz: opt.schwaerz ?? STANDARD_CONFIG,
  };
  patchFetch(ctx);
  patchXhr(ctx);
}

export function uninstallNetzwerk(): void {
  if (originalFetch) {
    if (globalThis.fetch === gepatchtFetch) globalThis.fetch = originalFetch;
    originalFetch = null;
    gepatchtFetch = null;
  }
  if (originalXhr) {
    const Proto = globalThis.XMLHttpRequest.prototype;
    Proto.open = originalXhr.open;
    Proto.send = originalXhr.send;
    Proto.setRequestHeader = originalXhr.setRequestHeader;
    originalXhr = null;
  }
}
