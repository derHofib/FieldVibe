// @vitest-environment jsdom
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { installNetzwerk, kuerzeText, uninstallNetzwerk } from "../netzwerk";
import { Ringpuffer } from "../ringpuffer";
import type { NetzwerkEintrag } from "../typen";

const urspruenglichesFetch = globalThis.fetch;
let puffer: Ringpuffer<NetzwerkEintrag>;

function tick() {
  return new Promise((r) => setTimeout(r, 20));
}

beforeEach(() => {
  puffer = new Ringpuffer<NetzwerkEintrag>(50);
});

afterEach(() => {
  uninstallNetzwerk();
  globalThis.fetch = urspruenglichesFetch;
  vi.restoreAllMocks();
});

describe("Ringpuffer", () => {
  it("haelt nur die letzten N Eintraege, aelteste zuerst", () => {
    const p = new Ringpuffer<number>(3);
    [1, 2, 3, 4, 5].forEach((n) => p.push(n));
    expect(p.toArray()).toEqual([3, 4, 5]);
    p.clear();
    expect(p.toArray()).toEqual([]);
    p.push(9);
    expect(p.toArray()).toEqual([9]);
  });
});

describe("kuerzeText", () => {
  it("kuerzt mit Markierung, kurze Texte bleiben", () => {
    expect(kuerzeText("abc", 10)).toBe("abc");
    const r = kuerzeText("a".repeat(100), 10);
    expect(r.startsWith("aaaaaaaaaa")).toBe(true);
    expect(r).toContain("gekuerzt");
  });
});

describe("fetch-Interceptor", () => {
  it("laesst die Response fuer den Aufrufer unveraendert lesbar und erfasst Bodies nicht bei Erfolg", async () => {
    const res = new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } });
    const stub = vi.fn().mockResolvedValue(res);
    globalThis.fetch = stub as unknown as typeof fetch;
    installNetzwerk({ puffer });

    const antwort = await fetch("http://localhost/api/x", { method: "post", body: JSON.stringify({ a: 1 }) });
    expect(antwort).toBe(res);
    expect(antwort.status).toBe(200);
    expect(await antwort.json()).toEqual({ ok: true });
    await tick();

    const [e] = puffer.toArray();
    expect(e.methode).toBe("POST");
    expect(e.status).toBe(200);
    expect(e.request_body).toBeUndefined();
    expect(e.response_body).toBeUndefined();
    expect(e.response_headers?.["content-type"]).toBe("application/json");
    expect(typeof e.dauer_ms).toBe("number");
  });

  it("erfasst bei Status >= 400 geschwaerzte Bodies, Original bleibt lesbar", async () => {
    const res = new Response(JSON.stringify({ detail: "kaputt", token: "geheim" }), {
      status: 500,
      headers: { "content-type": "application/json" },
    });
    globalThis.fetch = vi.fn().mockResolvedValue(res) as unknown as typeof fetch;
    installNetzwerk({ puffer });

    const antwort = await fetch("http://localhost/api/x", {
      method: "POST",
      headers: { Authorization: "Bearer abcdefghijkl" },
      body: JSON.stringify({ passwort: "pw", name: "a" }),
    });
    expect(await antwort.json()).toEqual({ detail: "kaputt", token: "geheim" });
    await tick();

    const [e] = puffer.toArray();
    expect(e.status).toBe(500);
    expect(JSON.parse(e.request_body!)).toEqual({ passwort: "[entfernt]", name: "a" });
    expect(JSON.parse(e.response_body!)).toEqual({ detail: "kaputt", token: "[entfernt]" });
    expect(e.request_headers?.authorization).toBe("[entfernt]");
  });

  it("kuerzt lange Bodies auf maxBodyBytes", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(new Response("x".repeat(500), { status: 400 })) as unknown as typeof fetch;
    installNetzwerk({ puffer, maxBodyBytes: 100 });
    await fetch("http://localhost/api/x");
    await tick();
    const body = puffer.toArray()[0].response_body!;
    expect(body.startsWith("x".repeat(100))).toBe(true);
    expect(body.length).toBeLessThan(200);
    expect(body).toContain("gekuerzt");
  });

  it("markiert Binaer-/FormData-Bodies statt sie zu lesen", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(new Response(new Uint8Array(7), { status: 404, headers: { "content-type": "image/png" } })) as unknown as typeof fetch;
    installNetzwerk({ puffer });
    await fetch("http://localhost/a", { method: "POST", body: new Blob([new Uint8Array(12)]) });
    await fetch("http://localhost/b", { method: "POST", body: new FormData() });
    await tick();
    const [a, b] = puffer.toArray();
    expect(a.request_body).toBe("[binär, 12 Bytes]");
    expect(a.response_body).toBe("[binär, 7 Bytes]");
    expect(b.request_body).toBe("[FormData]");
  });

  it("wirft Netzwerkfehler unveraendert weiter und erfasst sie samt Request-Body", async () => {
    const fehler = new TypeError("Failed to fetch");
    globalThis.fetch = vi.fn().mockRejectedValue(fehler) as unknown as typeof fetch;
    installNetzwerk({ puffer });

    await expect(fetch("http://localhost/api/x", { method: "POST", body: "a=1&password=x" })).rejects.toBe(fehler);
    await tick();
    const [e] = puffer.toArray();
    expect(e.status).toBe(0);
    expect(e.fehler).toContain("Failed to fetch");
    expect(e.request_body).toBe("a=1&password=[entfernt]");
  });

  it("reicht synchrone Exceptions der Original-Funktion durch", () => {
    const fehler = new Error("sync");
    globalThis.fetch = vi.fn(() => {
      throw fehler;
    }) as unknown as typeof fetch;
    installNetzwerk({ puffer });
    expect(() => fetch("http://localhost/x")).toThrow(fehler);
  });

  it("ignoriert den eigenen Upload-Endpoint und konfigurierte ignoreUrls", async () => {
    globalThis.fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response("", { status: 200 }))) as unknown as typeof fetch;
    installNetzwerk({ puffer, ignoreUrls: ["/health", /\/metrics$/] });
    await fetch("http://localhost/api/fehlerberichte");
    await fetch("http://localhost/health/live");
    await fetch("http://localhost/metrics");
    await fetch("http://localhost/api/andere");
    await tick();
    expect(puffer.toArray().map((e) => e.url)).toEqual(["http://localhost/api/andere"]);
  });

  it("schwaerzt Query-Parameter in der URL", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(new Response("", { status: 200 })) as unknown as typeof fetch;
    installNetzwerk({ puffer });
    await fetch("http://localhost/api/x?token=abc&a=1");
    await tick();
    expect(puffer.toArray()[0].url).toBe("http://localhost/api/x?token=[entfernt]&a=1");
  });

  it("respektiert die Ringpuffer-Grenze", async () => {
    puffer = new Ringpuffer<NetzwerkEintrag>(3);
    globalThis.fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response("", { status: 200 }))) as unknown as typeof fetch;
    installNetzwerk({ puffer });
    for (let i = 0; i < 5; i += 1) await fetch(`http://localhost/api/${i}`);
    await tick();
    expect(puffer.toArray().map((e) => e.url)).toEqual(["http://localhost/api/2", "http://localhost/api/3", "http://localhost/api/4"]);
  });

  it("ist idempotent und uninstall stellt das Original wieder her", async () => {
    const stub = vi.fn().mockImplementation(() => Promise.resolve(new Response("", { status: 200 })));
    globalThis.fetch = stub as unknown as typeof fetch;
    installNetzwerk({ puffer });
    const gepatcht = globalThis.fetch;
    installNetzwerk({ puffer });
    expect(globalThis.fetch).toBe(gepatcht);
    await fetch("http://localhost/api/x");
    await tick();
    expect(puffer.laenge).toBe(1);
    uninstallNetzwerk();
    expect(globalThis.fetch).toBe(stub);
  });
});

describe("XMLHttpRequest-Interceptor", () => {
  let server: Server;
  let basis: string;

  beforeEach(async () => {
    server = createServer((req, res) => {
      res.setHeader("Access-Control-Allow-Origin", "*");
      res.setHeader("Access-Control-Allow-Headers", "*");
      if (req.method === "OPTIONS") {
        res.statusCode = 204;
        res.end();
        return;
      }
      res.statusCode = req.url?.startsWith("/fehler") ? 500 : 200;
      res.setHeader("content-type", "application/json");
      res.end(JSON.stringify({ token: "geheim", ok: res.statusCode === 200 }));
    });
    await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
    basis = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  });

  afterEach(() => new Promise<void>((r) => server.close(() => r())));

  function xhr(methode: string, url: string, body?: string): Promise<XMLHttpRequest> {
    return new Promise((resolve) => {
      const x = new XMLHttpRequest();
      x.open(methode, url);
      x.setRequestHeader("X-Test", "1");
      x.addEventListener("loadend", () => resolve(x));
      x.send(body);
    });
  }

  it("erfasst Erfolg ohne Bodies, Aufrufer sieht die Antwort", async () => {
    installNetzwerk({ puffer });
    const x = await xhr("GET", `${basis}/ok`);
    await tick();
    expect(x.status).toBe(200);
    expect(JSON.parse(x.responseText).ok).toBe(true);
    const [e] = puffer.toArray();
    expect(e.status).toBe(200);
    expect(e.methode).toBe("GET");
    expect(e.request_headers?.["x-test"]).toBe("1");
    expect(e.response_body).toBeUndefined();
  });

  it("erfasst bei Fehlerstatus geschwaerzte Bodies", async () => {
    installNetzwerk({ puffer });
    const x = await xhr("POST", `${basis}/fehler`, JSON.stringify({ password: "x" }));
    await tick();
    expect(x.status).toBe(500);
    const [e] = puffer.toArray();
    expect(JSON.parse(e.request_body!)).toEqual({ password: "[entfernt]" });
    expect(JSON.parse(e.response_body!)).toEqual({ token: "[entfernt]", ok: false });
  });

  it("erfasst Netzwerkfehler", async () => {
    installNetzwerk({ puffer });
    const x = await xhr("GET", "http://127.0.0.1:1/nix");
    await tick();
    expect(x.status).toBe(0);
    const [e] = puffer.toArray();
    expect(e.fehler).toBeTruthy();
    expect(e.status).toBe(0);
  });

  it("stellt das Original bei uninstall wieder her", () => {
    const open = XMLHttpRequest.prototype.open;
    installNetzwerk({ puffer });
    expect(XMLHttpRequest.prototype.open).not.toBe(open);
    uninstallNetzwerk();
    expect(XMLHttpRequest.prototype.open).toBe(open);
  });
});
