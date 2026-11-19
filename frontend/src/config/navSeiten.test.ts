import { describe, expect, it } from "vitest";

import { NAV_SEITEN, effektiveNavGruppen } from "./navSeiten";

describe("Nav-Anpassungen mit entfernter Seite", () => {
  it("ein gespeicherter Schlüssel techniker_zuweisungen wird stillschweigend ignoriert", () => {
    expect(NAV_SEITEN.some((s) => s.key === "techniker_zuweisungen")).toBe(false);
    const kunden = NAV_SEITEN.filter((s) => s.key === "kunden");
    const gruppen = effektiveNavGruppen(kunden, {
      kategorien: [{ name: "Eigene", reihenfolge: 0 }],
      zuordnungen: { techniker_zuweisungen: "Eigene", kunden: "Eigene" },
    } as never);
    expect(gruppen).toHaveLength(1);
    expect(gruppen[0].seiten.map((s) => s.key)).toEqual(["kunden"]);
  });
});
