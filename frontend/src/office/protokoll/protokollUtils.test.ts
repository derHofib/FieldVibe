import { describe, expect, it } from "vitest";

import { aktionLabel, detailsText, filterQuery, seitenText } from "./protokollUtils";

describe("protokollUtils", () => {
  it("benennt bekannte Aktionen und leitet unbekannte aus dem Schluessel ab", () => {
    expect(aktionLabel("rechnung_versendet")).toBe("Rechnung versendet");
    expect(aktionLabel("fehlerbericht.service_zugriff")).toBe("Fehlerbericht service zugriff");
  });

  it("laesst leere Filter weg", () => {
    expect(filterQuery({ von: "2026-01-01", bis: "", aktion: undefined }, { limit: 50 })).toBe("von=2026-01-01&limit=50");
  });

  it("kuerzt lange Details", () => {
    expect(detailsText({ a: 1, b: { c: 2 } })).toBe('a: 1 · b: {"c":2}');
    expect(detailsText({ text: "x".repeat(300) }, 20)).toHaveLength(20);
  });

  it("formuliert die Seitenangabe", () => {
    expect(seitenText(0, 0, 0)).toBe("Keine Einträge");
    expect(seitenText(50, 50, 120)).toBe("51–100 von 120");
  });
});
