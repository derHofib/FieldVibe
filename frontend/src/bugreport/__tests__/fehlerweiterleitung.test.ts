// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  beendeFehlerweiterleitung,
  installFehlerweiterleitung,
  normalisierePfad,
  parseDsn,
} from "../fehlerweiterleitung";

const DSN = "https://publickey@errors.example.eu/42";

function fehlerEvent(error: Error | null, message = "x") {
  const ev = new Event("error") as ErrorEvent;
  Object.assign(ev, { error, message });
  window.dispatchEvent(ev);
}

function sendeBody(fetchFn: ReturnType<typeof vi.fn>, i = 0): { kopf: any; item: any; event: any } {
  const [kopf, item, event] = (fetchFn.mock.calls[i][1].body as string).split("\n").map((z) => JSON.parse(z));
  return { kopf, item, event };
}

let fetchFn: ReturnType<typeof vi.fn>;
let zeit: number;

beforeEach(() => {
  fetchFn = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
  zeit = 1_000_000;
});

afterEach(() => {
  beendeFehlerweiterleitung();
});

const cfg = () => ({
  dsn: DSN,
  release: "1.0.0+abc",
  environment: "production",
  fetchFn: fetchFn as unknown as typeof fetch,
  jetzt: () => zeit,
});

describe("DSN und Pfade", () => {
  it("zerlegt die DSN in Envelope-URL und Schluessel", () => {
    expect(parseDsn(DSN)).toEqual({ url: "https://errors.example.eu/api/42/envelope/", schluessel: "publickey" });
  });

  it("lehnt unbrauchbare DSNs ab", () => {
    expect(parseDsn("")).toBeNull();
    expect(parseDsn("kein url")).toBeNull();
    expect(parseDsn("https://errors.example.eu/42")).toBeNull();
    expect(installFehlerweiterleitung({ ...cfg(), dsn: "" })).toBe(false);
  });

  it("entfernt Query, IDs und Tokens aus dem Pfad", () => {
    expect(normalisierePfad("/kunden/0f8fad5b-d9cb-469f-a165-70867728950e/edit?token=abc#x")).toBe("/kunden/:id/edit");
    expect(normalisierePfad("/vorgaenge/123456")).toBe("/vorgaenge/:n");
    expect(normalisierePfad("/reset/abcdefghijklmnopqrstuvwxyz0123")).toBe("/reset/:token");
  });
});

describe("Weiterleitung", () => {
  it("sendet einen unbehandelten Fehler mit Release, Umgebung und ohne Cookies/Credentials", () => {
    installFehlerweiterleitung(cfg());
    fehlerEvent(new TypeError("kaputt"));
    expect(fetchFn).toHaveBeenCalledTimes(1);
    const [url, init] = fetchFn.mock.calls[0];
    expect(url).toBe("https://errors.example.eu/api/42/envelope/?sentry_key=publickey&sentry_version=7");
    expect(init.credentials).toBe("omit");
    expect(init.headers["Content-Type"]).toBe("text/plain;charset=UTF-8");
    const { item, event } = sendeBody(fetchFn);
    expect(item.type).toBe("event");
    expect(event.release).toBe("1.0.0+abc");
    expect(event.environment).toBe("production");
    expect(event.exception.values[0]).toEqual({ type: "TypeError", value: "kaputt" });
    expect(event.user).toBeUndefined();
  });

  it("schwaerzt Tokens, E-Mails und IBANs in Meldung und Stack", () => {
    installFehlerweiterleitung(cfg());
    const err = new Error("Login ok@firma.de password=hunter2 DE89370400440532013000");
    err.stack = "Error: x\n at f (Bearer abcdefghijkl)";
    fehlerEvent(err);
    const roh = fetchFn.mock.calls[0][1].body as string;
    for (const geheim of ["ok@firma.de", "hunter2", "DE89370400440532013000", "abcdefghijkl"]) {
      expect(roh).not.toContain(geheim);
    }
  });

  it("uebernimmt weder Query noch Fragment der Seite", () => {
    window.history.pushState({}, "", "/portal/reset?token=geheim123#abc");
    installFehlerweiterleitung(cfg());
    fehlerEvent(new Error("x1"));
    const roh = fetchFn.mock.calls[0][1].body as string;
    expect(roh).not.toContain("geheim123");
    expect(sendeBody(fetchFn).event.request.url).toMatch(/\/portal\/reset$/);
  });

  it("meldet unbehandelte Promise-Rejections", () => {
    installFehlerweiterleitung(cfg());
    const ev = new Event("unhandledrejection") as PromiseRejectionEvent;
    Object.assign(ev, { reason: new RangeError("zu gross") });
    window.dispatchEvent(ev);
    expect(sendeBody(fetchFn).event.exception.values[0].value).toContain("zu gross");
  });

  it("ignoriert Offline-Rauschen", () => {
    installFehlerweiterleitung(cfg());
    fehlerEvent(new TypeError("Failed to fetch"));
    fehlerEvent(null, "ResizeObserver loop completed with undelivered notifications.");
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it("dedupliziert gleiche Fehler und drosselt auf 10 pro Fenster", () => {
    installFehlerweiterleitung(cfg());
    fehlerEvent(new Error("gleich"));
    fehlerEvent(new Error("gleich"));
    expect(fetchFn).toHaveBeenCalledTimes(1);
    for (let i = 0; i < 20; i += 1) fehlerEvent(new Error(`anders ${i}`));
    expect(fetchFn).toHaveBeenCalledTimes(10);
    zeit += 6 * 60 * 1000;
    fehlerEvent(new Error("gleich"));
    expect(fetchFn).toHaveBeenCalledTimes(11);
  });

  it("verschluckt Netzwerkfehler beim Senden", async () => {
    fetchFn.mockRejectedValue(new TypeError("offline"));
    installFehlerweiterleitung(cfg());
    expect(() => fehlerEvent(new Error("egal"))).not.toThrow();
    await Promise.resolve();
  });

  it("sampleRate 0 sendet nichts", () => {
    installFehlerweiterleitung({ ...cfg(), sampleRate: 0 });
    fehlerEvent(new Error("nie"));
    expect(fetchFn).not.toHaveBeenCalled();
  });
});
