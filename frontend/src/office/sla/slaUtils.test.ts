import { describe, expect, it } from "vitest";

import { dauerText, fensterAus, minutenOderLeer, zeitenAus } from "./slaUtils";

describe("slaUtils", () => {
  it("wandelt Wochentage und Fenster ineinander um", () => {
    const zeiten = zeitenAus([0, 1, 4], "08:00", "16:30");
    expect(zeiten).toEqual({ "0": [["08:00", "16:30"]], "1": [["08:00", "16:30"]], "4": [["08:00", "16:30"]] });
    expect(fensterAus(zeiten)).toEqual({ tage: [0, 1, 4], von: "08:00", bis: "16:30" });
  });

  it("liefert ohne Zeiten Mo–Fr 07–17", () => {
    expect(fensterAus({})).toEqual({ tage: [0, 1, 2, 3, 4], von: "07:00", bis: "17:00" });
  });

  it("liest Minuten nur für positive Zahlen", () => {
    expect(minutenOderLeer("30")).toBe(30);
    expect(minutenOderLeer("")).toBeUndefined();
    expect(minutenOderLeer("0")).toBeUndefined();
    expect(minutenOderLeer("abc")).toBeUndefined();
  });

  it("formatiert Dauern", () => {
    expect(dauerText(null)).toBe("—");
    expect(dauerText(45)).toBe("45 Min.");
    expect(dauerText(135)).toBe("2 Std. 15 Min.");
    expect(dauerText(2880)).toBe("2 Tg.");
  });
});
