import { afterEach, describe, expect, it, vi } from "vitest";

import { heuteIso, lokalesDatum } from "./format";

describe("lokalesDatum", () => {
  it("nutzt den lokalen Kalendertag, nicht UTC", () => {
    // 00:30 Ortszeit läge in UTC (Zeitzonen östlich von UTC) noch am Vortag
    expect(lokalesDatum(new Date(2026, 2, 5, 0, 30))).toBe("2026-03-05");
    expect(lokalesDatum(new Date(2026, 2, 5, 23, 30))).toBe("2026-03-05");
  });
});

describe("heuteIso", () => {
  afterEach(() => vi.useRealTimers());

  it("liefert nach Mitternacht den heutigen Tag", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 0, 31, 0, 15));
    expect(heuteIso()).toBe("2026-01-31");
    expect(heuteIso(1)).toBe("2026-02-01");
  });
});
