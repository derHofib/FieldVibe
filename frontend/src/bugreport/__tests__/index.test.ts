// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

import { beendeFehlerbericht, initFehlerbericht, registriereDebugState, sammleKontext } from "../index";

const gesichert = { error: console.error, warn: console.warn, log: console.log, fetch: globalThis.fetch };

afterEach(() => {
  beendeFehlerbericht();
  Object.assign(console, { error: gesichert.error, warn: gesichert.warn, log: gesichert.log });
  globalThis.fetch = gesichert.fetch;
});

const basis = { appVersion: "1.2.3", commitSha: "abc123", getSitzung: () => ({ user_id: "u1", mandant_id: "m1", rolle: "admin" }) };

describe("sammleKontext", () => {
  it("liefert alle Kategorien mit den erwarteten Feldnamen", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(new Response("nope", { status: 500 })) as unknown as typeof fetch;
    initFehlerbericht(basis);
    console.error("anna@example.com hat ein Problem");
    await fetch("http://localhost/api/x?token=abc");
    await new Promise((r) => setTimeout(r, 20));

    const k = sammleKontext();
    expect(Object.keys(k).sort()).toEqual(["app_state", "breadcrumbs", "konsole", "netzwerk", "sitzung", "umgebung"]);
    expect(k.konsole![0].nachricht).toBe("[email] hat ein Problem");
    expect(k.netzwerk![0].url).toContain("token=[entfernt]");
    expect(k.netzwerk![0].response_body).toBe("nope");
    expect(k.sitzung).toEqual({ user_id: "u1", mandant_id: "m1", rolle: "admin" });
    expect(k.umgebung).toMatchObject({ app_version: "1.2.3", commit_sha: "abc123" });
    expect(k.umgebung!.viewport).toHaveProperty("breite");
  });

  it("liefert nur die gewaehlten Kategorien", () => {
    initFehlerbericht(basis);
    expect(Object.keys(sammleKontext(["sitzung"]))).toEqual(["sitzung"]);
  });

  it("verkraftet eine werfende getSitzung und liefert leere Sitzung", () => {
    initFehlerbericht({
      ...basis,
      getSitzung: () => {
        throw new Error("x");
      },
    });
    expect(sammleKontext(["sitzung"]).sitzung).toEqual({});
  });

  it("Debug-State: schwaerzt, faengt Fehler ab, Abmelden funktioniert", () => {
    initFehlerbericht(basis);
    const ab = registriereDebugState("filter", () => ({ status: "offen", token: "geheim" }));
    registriereDebugState("kaputt", () => {
      throw new Error("oops");
    });
    const k = sammleKontext(["app_state"]);
    expect(k.app_state!.filter).toEqual({ status: "offen", token: "[entfernt]" });
    expect(k.app_state!.kaputt).toContain("oops");
    ab();
    expect(sammleKontext(["app_state"]).app_state).not.toHaveProperty("filter");
    // aufraeumen
    registriereDebugState("kaputt", () => 1)();
  });

  it("kuerzt zu grossen Debug-State", () => {
    initFehlerbericht(basis);
    const ab = registriereDebugState("gross", () => ({ a: "z".repeat(50_000) }));
    const wert = sammleKontext(["app_state"]).app_state!.gross as string;
    expect(typeof wert).toBe("string");
    expect(wert.length).toBeLessThan(10_100);
    ab();
  });

  it("zusatzDenylist und maskiereEmail greifen", () => {
    initFehlerbericht({ ...basis, zusatzDenylist: ["kundennr"], maskiereEmail: false });
    const ab = registriereDebugState("k", () => ({ kundennr: "1", mail: "a@b.de" }));
    expect(sammleKontext(["app_state"]).app_state!.k).toEqual({ kundennr: "[entfernt]", mail: "a@b.de" });
    ab();
  });

  it("respektiert maxKonsole", () => {
    initFehlerbericht({ ...basis, maxKonsole: 2 });
    console.log("1");
    console.log("2");
    console.log("3");
    expect(sammleKontext(["konsole"]).konsole!.map((e) => e.nachricht)).toEqual(["2", "3"]);
  });
});
