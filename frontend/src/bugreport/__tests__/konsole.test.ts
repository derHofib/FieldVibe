// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { installKonsole, uninstallKonsole } from "../konsole";
import { Ringpuffer } from "../ringpuffer";
import type { KonsolenEintrag } from "../typen";

let puffer: Ringpuffer<KonsolenEintrag>;
let origError: Mock;
let origWarn: Mock;
let origLog: Mock;
const gesichert = { error: console.error, warn: console.warn, log: console.log };

beforeEach(() => {
  puffer = new Ringpuffer<KonsolenEintrag>(100);
  origError = vi.fn();
  origWarn = vi.fn();
  origLog = vi.fn();
  console.error = origError as unknown as typeof console.error;
  console.warn = origWarn as unknown as typeof console.warn;
  console.log = origLog as unknown as typeof console.log;
});

afterEach(() => {
  uninstallKonsole();
  Object.assign(console, gesichert);
});

describe("Konsole", () => {
  it("erfasst Error-Objekte mit Stack und ruft das Original weiter auf", () => {
    installKonsole({ puffer });
    const err = new Error("boom");
    console.error("Fehler:", err);
    const [e] = puffer.toArray();
    expect(e.level).toBe("error");
    expect(e.nachricht).toContain("Fehler: Error: boom");
    expect(e.stack).toContain("boom");
    expect(origError).toHaveBeenCalledWith("Fehler:", err);
  });

  it("serialisiert Objekte mit Zyklen, schwaerzt Secrets und kuerzt auf 2000 Zeichen", () => {
    installKonsole({ puffer });
    const o: Record<string, unknown> = { password: "geheim", gross: "y".repeat(5000) };
    o.self = o;
    console.warn(o);
    const [e] = puffer.toArray();
    expect(e.level).toBe("warn");
    expect(e.nachricht).not.toContain("geheim");
    expect(e.nachricht.length).toBeLessThan(2100);
    expect(origWarn).toHaveBeenCalledWith(o);
  });

  it("schaltet console.log per Config ab", () => {
    installKonsole({ puffer, konsoleLog: false });
    console.log("still");
    expect(puffer.laenge).toBe(0);
    expect(origLog).toHaveBeenCalledWith("still");
  });

  it("erfasst log standardmaessig", () => {
    installKonsole({ puffer });
    console.log("hallo", 42);
    expect(puffer.toArray()[0]).toMatchObject({ level: "log", nachricht: "hallo 42" });
  });

  it("erfasst window error mit Stack", () => {
    installKonsole({ puffer });
    const fehler = new Error("global kaputt");
    window.dispatchEvent(new ErrorEvent("error", { message: "global kaputt", error: fehler }));
    const [e] = puffer.toArray();
    expect(e.nachricht).toContain("global kaputt");
    expect(e.stack).toContain("global kaputt");
  });

  it("erfasst unhandledrejection mit Stack", () => {
    installKonsole({ puffer });
    const reason = new Error("abgelehnt");
    const ev = new Event("unhandledrejection") as Event & { reason: unknown };
    ev.reason = reason;
    window.dispatchEvent(ev);
    const [e] = puffer.toArray();
    expect(e.nachricht).toContain("Unhandled Promise Rejection: Error: abgelehnt");
    expect(e.stack).toContain("abgelehnt");
  });

  it("stellt die Original-Console beim uninstall wieder her", () => {
    installKonsole({ puffer });
    uninstallKonsole();
    expect(console.error).toBe(origError);
  });
});
