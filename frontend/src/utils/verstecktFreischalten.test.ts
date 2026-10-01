import { describe, expect, it } from "vitest";

import { istVersteckteTastenkombi, klickFolge } from "./verstecktFreischalten";

function klicks(zeitpunkte: number[]): boolean {
  let zeiten: number[] = [];
  let erreicht = false;
  for (const t of zeitpunkte) {
    ({ zeiten, erreicht } = klickFolge(zeiten, t));
  }
  return erreicht;
}

describe("klickFolge", () => {
  it("erkennt 5 Klicks innerhalb von 2 s", () => {
    expect(klicks([0, 400, 800, 1200, 1600])).toBe(true);
  });
  it("erkennt 4 Klicks nicht", () => {
    expect(klicks([0, 400, 800, 1200])).toBe(false);
  });
  it("erkennt zu langsame Klicks nicht", () => {
    expect(klicks([0, 600, 1200, 1800, 2400])).toBe(false);
  });
  it("beginnt nach Erfolg neu", () => {
    expect(klicks([0, 100, 200, 300, 400, 500])).toBe(false);
  });
});

describe("istVersteckteTastenkombi", () => {
  it("prueft code statt key", () => {
    expect(istVersteckteTastenkombi({ code: "KeyP", shiftKey: true, altKey: true })).toBe(true);
    expect(istVersteckteTastenkombi({ code: "KeyP", shiftKey: false, altKey: true })).toBe(false);
    expect(istVersteckteTastenkombi({ code: "KeyO", shiftKey: true, altKey: true })).toBe(false);
  });
});
