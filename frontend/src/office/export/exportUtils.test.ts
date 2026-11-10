import { describe, expect, it } from "vitest";

import { aktiverExportVorhanden, parameterText, resttage, standardZeitraum, zeitraumGueltig } from "./exportUtils";

describe("exportUtils", () => {
  it("nimmt das Vorjahr als Standardzeitraum", () => {
    expect(standardZeitraum(new Date("2026-10-21T10:00:00"))).toEqual({ von: "2025-01-01", bis: "2025-12-31" });
  });

  it("prueft den Zeitraum wie das Backend", () => {
    expect(zeitraumGueltig("2025-01-01", "2025-12-31")).toBeNull();
    expect(zeitraumGueltig("", "2025-12-31")).toMatch(/Zeitraum/);
    expect(zeitraumGueltig("2025-02-01", "2025-01-01")).toMatch(/nicht vor/);
    expect(zeitraumGueltig("2010-01-01", "2026-01-01")).toMatch(/fünf Jahre/);
  });

  it("erkennt laufende Exporte", () => {
    expect(aktiverExportVorhanden([{ status: "fertig" }, { status: "laeuft" }])).toBe(true);
    expect(aktiverExportVorhanden([{ status: "fertig" }, { status: "fehler" }, { status: "abgelaufen" }])).toBe(false);
    expect(aktiverExportVorhanden([{ status: "wartend" }])).toBe(true);
  });

  it("zeigt den Zeitraum nur bei Z3", () => {
    expect(parameterText({ art: "vollexport", parameter: {} })).toBe("");
    expect(parameterText({ art: "z3", parameter: { von: "2025-01-01", bis: "2025-12-31" } })).toBe("01.01.2025 – 31.12.2025");
  });

  it("rechnet die Resttage", () => {
    const jetzt = new Date("2026-10-21T12:00:00Z");
    expect(resttage("2026-10-28T12:00:00Z", jetzt)).toBe(7);
    expect(resttage("2026-10-20T12:00:00Z", jetzt)).toBe(0);
    expect(resttage(null, jetzt)).toBeNull();
  });
});
