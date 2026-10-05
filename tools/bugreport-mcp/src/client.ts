export const STATI = ["neu", "gesichtet", "in_arbeit", "behoben", "abgelehnt", "duplikat"] as const;
export const SCHWEREGRADE = ["niedrig", "mittel", "hoch", "blockierend"] as const;
export const ARTEN = ["fehler", "idee"] as const;
export type Status = (typeof STATI)[number];
export type Art = (typeof ARTEN)[number];
export type Schweregrad = (typeof SCHWEREGRADE)[number];

export const SCREENSHOT_MAX_BYTES = 2 * 1024 * 1024;

export class ApiFehler extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiFehler";
  }
}

export interface ClientConfig {
  baseUrl: string;
  token: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

export interface UpdateEingabe {
  id: string;
  status: Status;
  resolution_note?: string;
  fix_commit?: string;
  fix_pr_url?: string;
}

export interface Screenshot {
  art: "original" | "annotiert";
  url: string;
  mimeType?: string;
  base64?: string;
}

export function meldungFuerStatus(status: number, detail: string): string {
  switch (status) {
    case 401:
      return "Token ungueltig (FIELDVIBE_BUGREPORT_TOKEN pruefen).";
    case 404:
      return "Nicht gefunden (Bericht-ID falsch oder Service-API serverseitig nicht aktiviert).";
    case 403:
      return `Nicht erlaubt: ${detail}`;
    case 409:
      return `Konflikt: ${detail}`;
    case 422:
      return `Eingabe abgelehnt: ${detail}`;
    case 429:
      return "Rate-Limit erreicht, spaeter erneut versuchen.";
    default:
      return `HTTP ${status}: ${detail}`;
  }
}

export function baueUpdateBody(e: UpdateEingabe): Record<string, string> {
  const body: Record<string, string> = { status: e.status };
  if (e.resolution_note !== undefined) body.loesungsnotiz = e.resolution_note;
  if (e.fix_commit !== undefined) body.fix_commit = e.fix_commit;
  if (e.fix_pr_url !== undefined) body.fix_pr_url = e.fix_pr_url;
  return body;
}

export class BugreportClient {
  private readonly basis: string;
  private readonly fetchImpl: typeof fetch;
  private readonly timeoutMs: number;

  constructor(private readonly cfg: ClientConfig) {
    this.basis = `${cfg.baseUrl.replace(/\/+$/, "")}/api/service/fehlerberichte`;
    this.fetchImpl = cfg.fetchImpl ?? fetch;
    this.timeoutMs = cfg.timeoutMs ?? 30_000;
  }

  private async anfrage(pfad: string, init: RequestInit = {}): Promise<Response> {
    let res: Response;
    try {
      res = await this.fetchImpl(`${this.basis}${pfad}`, {
        ...init,
        headers: {
          ...(init.headers as Record<string, string> | undefined),
          Authorization: `Bearer ${this.cfg.token}`,
        },
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (e) {
      const timeout = e instanceof Error && (e.name === "TimeoutError" || e.name === "AbortError");
      // Originaltext des Fehlers bewusst nicht durchreichen.
      throw new ApiFehler(timeout ? `Zeitueberschreitung nach ${this.timeoutMs} ms` : "Verbindung zur API fehlgeschlagen");
    }
    if (!res.ok) {
      const detail = (await res.text().catch(() => "")).slice(0, 300);
      throw new ApiFehler(meldungFuerStatus(res.status, detail), res.status);
    }
    return res;
  }

  async liste(f: { status?: Status; severity?: Schweregrad; kind?: Art; since?: string; limit?: number }): Promise<unknown[]> {
    const q = new URLSearchParams();
    if (f.status) q.set("status", f.status);
    if (f.severity) q.set("schweregrad", f.severity);
    if (f.kind) q.set("art", f.kind);
    if (f.since) q.set("seit", f.since);
    if (f.limit) q.set("limit", String(f.limit));
    const qs = q.toString();
    return (await (await this.anfrage(qs ? `?${qs}` : "")).json()) as unknown[];
  }

  async detail(id: string): Promise<Record<string, unknown>> {
    return (await (await this.anfrage(`/${encodeURIComponent(id)}`)).json()) as Record<string, unknown>;
  }

  async aiBundle(id: string): Promise<string> {
    return (await this.anfrage(`/${encodeURIComponent(id)}/ai-bundle`)).text();
  }

  async aehnliche(id: string): Promise<unknown[]> {
    return (await (await this.anfrage(`/${encodeURIComponent(id)}/aehnliche`)).json()) as unknown[];
  }

  async update(e: UpdateEingabe): Promise<Record<string, unknown>> {
    const res = await this.anfrage(`/${encodeURIComponent(e.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(baueUpdateBody(e)),
    });
    return (await res.json()) as Record<string, unknown>;
  }

  // Presigned-URL geht direkt an S3/MinIO -- ohne Authorization-Header.
  async ladeScreenshot(art: Screenshot["art"], url: string): Promise<Screenshot> {
    const basis: Screenshot = { art, url };
    try {
      const res = await this.fetchImpl(url, { signal: AbortSignal.timeout(this.timeoutMs) });
      if (!res.ok) return basis;
      const laenge = Number(res.headers.get("content-length") ?? "0");
      if (laenge > SCREENSHOT_MAX_BYTES) return basis;
      const buf = Buffer.from(await res.arrayBuffer());
      if (buf.byteLength > SCREENSHOT_MAX_BYTES) return basis;
      const mimeType = (res.headers.get("content-type") ?? "image/png").split(";")[0].trim();
      return { ...basis, mimeType, base64: buf.toString("base64") };
    } catch {
      return basis;
    }
  }
}
