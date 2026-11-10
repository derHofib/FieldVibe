import { describe, expect, it } from "vitest";

import { absaetze, widerrufFristLetzterTag } from "./portalAngebot";

describe("widerrufFristLetzterTag", () => {
  it("zeigt den Tag vor dem exklusiven Fristende (Berliner Zeit)", () => {
    // Backend: Fristende 16.03.2026 00:00 Ortszeit = 15.03. 23:00 UTC
    expect(widerrufFristLetzterTag("2026-03-15T23:00:00Z")).toBe("15.3.2026");
  });

  it("beachtet die Sommerzeit", () => {
    // 16.07.2026 00:00 Ortszeit (MESZ) = 15.07. 22:00 UTC
    expect(widerrufFristLetzterTag("2026-07-15T22:00:00Z")).toBe("15.7.2026");
  });
});

describe("absaetze", () => {
  it("trennt an Leerzeilen und verwirft leere Absaetze", () => {
    expect(absaetze("Eins\nzwei\n\n\nDrei\n\n  ")).toEqual(["Eins\nzwei", "Drei"]);
  });
});
