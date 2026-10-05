import { describe, expect, it, vi } from "vitest";
import { ApiFehler, BugreportClient, baueUpdateBody, meldungFuerStatus } from "./client.js";

const TOKEN = "geheim-token-123";

function antwort(body: unknown, init: ResponseInit = {}, raw = false) {
  return new Response(raw ? (body as string) : JSON.stringify(body), init);
}

function mk(fetchImpl: typeof fetch) {
  return new BugreportClient({ baseUrl: "https://api.example.de/", token: TOKEN, fetchImpl });
}

describe("baueUpdateBody", () => {
  it("mappt englische Eingaben auf deutsche Felder", () => {
    expect(
      baueUpdateBody({ id: "x", status: "behoben", resolution_note: "n", fix_commit: "abc", fix_pr_url: "u" }),
    ).toEqual({ status: "behoben", loesungsnotiz: "n", fix_commit: "abc", fix_pr_url: "u" });
  });
  it("laesst nicht gesetzte Felder weg", () => {
    expect(baueUpdateBody({ id: "x", status: "in_arbeit" })).toEqual({ status: "in_arbeit" });
  });
});

describe("meldungFuerStatus", () => {
  it.each([401, 403, 404, 409, 429])("liefert deutsche Meldung fuer %i", (s) => {
    expect(meldungFuerStatus(s, "")).not.toMatch(/^HTTP/);
  });
  it("faellt auf HTTP-Code zurueck", () => {
    expect(meldungFuerStatus(500, "boom")).toBe("HTTP 500: boom");
  });
});

describe("BugreportClient", () => {
  it("baut Query mit deutschen Parameternamen und sendet Bearer-Token", async () => {
    const f = vi.fn(async () => antwort([]));
    await mk(f as unknown as typeof fetch).liste({ status: "neu", severity: "hoch", since: "2026-01-01T00:00:00Z", limit: 5 });
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(
      "https://api.example.de/api/service/fehlerberichte?status=neu&schweregrad=hoch&seit=2026-01-01T00%3A00%3A00Z&limit=5",
    );
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
  });

  it("uebersetzt kind in den Query-Parameter art", async () => {
    const f = vi.fn(async () => antwort([]));
    await mk(f as unknown as typeof fetch).liste({ kind: "idee", status: "gesichtet" });
    const [url] = f.mock.calls[0] as unknown as [string];
    expect(url).toBe("https://api.example.de/api/service/fehlerberichte?status=gesichtet&art=idee");
  });

  it("sendet PATCH mit deutschem JSON-Body", async () => {
    const f = vi.fn(async () => antwort({ id: "x" }));
    await mk(f as unknown as typeof fetch).update({ id: "x", status: "behoben", resolution_note: "ok" });
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/fehlerberichte\/x$/);
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({ status: "behoben", loesungsnotiz: "ok" });
  });

  it("uebersetzt HTTP-Fehler ohne das Token preiszugeben", async () => {
    const f = vi.fn(async () => antwort("nope", { status: 401 }, true));
    const err = await mk(f as unknown as typeof fetch).detail("x").catch((e) => e);
    expect(err).toBeInstanceOf(ApiFehler);
    expect(err.status).toBe(401);
    expect(err.message).not.toContain(TOKEN);
  });

  it("meldet Netzwerkfehler verstaendlich", async () => {
    const f = vi.fn(async () => {
      throw new TypeError("fetch failed");
    });
    await expect(mk(f as unknown as typeof fetch).aiBundle("x")).rejects.toThrow(/Verbindung/);
  });

  it("liefert Screenshot als Base64 bis 2 MB", async () => {
    const f = vi.fn(async () => new Response(new Uint8Array([1, 2, 3]), { headers: { "content-type": "image/png" } }));
    const s = await mk(f as unknown as typeof fetch).ladeScreenshot("original", "https://s3/x.png");
    expect(s.base64).toBe("AQID");
    expect(s.mimeType).toBe("image/png");
    const init = (f.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init.headers).toBeUndefined();
  });

  it("gibt bei grossen Screenshots nur die URL zurueck", async () => {
    const f = vi.fn(async () => new Response("x", { headers: { "content-length": String(3 * 1024 * 1024) } }));
    const s = await mk(f as unknown as typeof fetch).ladeScreenshot("annotiert", "https://s3/y.png");
    expect(s.base64).toBeUndefined();
    expect(s.url).toBe("https://s3/y.png");
  });
});
