// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";

import type { CurrentUser, RechteAktion, RechteBereich, Role } from "../types";
import { sichtbareNavSeiten } from "./navSeiten";
import { routeErlaubt, type RoutenKontext } from "./routenRechte";

function kontext(
  role: Role,
  rechte: Partial<Record<RechteBereich, RechteAktion[]>> = {},
  oberflaeche: "office" | "feld" = "office",
): RoutenKontext {
  const currentUser = { role, rechte, deaktivierte_module: [] } as unknown as CurrentUser;
  return { currentUser, hatRecht: (b, a) => role !== "custom" || (rechte[b]?.includes(a) ?? false), oberflaeche };
}

afterEach(() => sessionStorage.clear());

describe("Kennzahlen: Routen und Menü", () => {
  it("Office: Büro-Rolle mit statistik.sehen darf /kennzahlen, ohne das Recht nicht", () => {
    sessionStorage.setItem("fieldvibe-office-dev", "1");
    expect(routeErlaubt("/kennzahlen", kontext("custom", { statistik: ["sehen"] }))).toBe(true);
    expect(routeErlaubt("/kennzahlen", kontext("custom", { vorgaenge: ["sehen"] }))).toBe(false);
    expect(routeErlaubt("/kennzahlen", kontext("mandant_admin"))).toBe(true);
    const keys = sichtbareNavSeiten(kontext("custom", { statistik: ["sehen"] }).currentUser, kontext("custom", { statistik: ["sehen"] }).hatRecht);
    expect(keys.find((s) => s.key === "kennzahlen")?.route).toBe("/kennzahlen");
  });

  it("Feld-App: /kennzahlen leitet auf /insights (nur Admin) -- Büro-Rollen bekommen dort keinen Eintrag", () => {
    const buero = kontext("custom", { statistik: ["sehen"] }, "feld");
    expect(routeErlaubt("/kennzahlen", buero)).toBe(false);
    expect(routeErlaubt("/insights", buero)).toBe(false);
    expect(sichtbareNavSeiten(buero.currentUser, buero.hatRecht, "feld").map((s) => s.key)).not.toContain("kennzahlen");
    const admin = kontext("mandant_admin", {}, "feld");
    expect(routeErlaubt("/kennzahlen", admin)).toBe(true);
    expect(routeErlaubt("/insights", admin)).toBe(true);
  });

  it("Office: /insights bleibt als Weiterleitung für jede Rolle erreichbar, die Zielseite prüft", () => {
    expect(routeErlaubt("/insights", kontext("custom", {}, "office"))).toBe(true);
  });

  it("Modul statistik aus: kein Zugriff", () => {
    const ctx = kontext("mandant_admin");
    (ctx.currentUser as { deaktivierte_module: string[] }).deaktivierte_module = ["statistik"];
    expect(routeErlaubt("/kennzahlen", ctx)).toBe(false);
  });
});
