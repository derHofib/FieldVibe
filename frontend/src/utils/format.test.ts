import { afterEach, describe, expect, it, vi } from "vitest";

import { datumZuIso, formatIsoTag, heuteIso, tageZwischen } from "./format";

afterEach(() => vi.useRealTimers());

describe("datumZuIso / heuteIso", () => {
  it("nutzt den lokalen Kalendertag, nicht den UTC-Tag", () => {
    // 00:30 Ortszeit: UTC liegt (je nach Zone) noch auf dem Vortag.
    expect(datumZuIso(new Date(2026, 9, 19, 0, 30))).toBe("2026-10-19");
    expect(datumZuIso(new Date(2026, 0, 5, 23, 59))).toBe("2026-01-05");
  });

  it("rechnet Offsets über Monatsgrenzen", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 9, 31, 12, 0));
    expect(heuteIso()).toBe("2026-10-31");
    expect(heuteIso(1)).toBe("2026-11-01");
  });
});

describe("tageZwischen", () => {
  it("zählt Kalendertage auch über die Sommerzeitumstellung", () => {
    expect(tageZwischen("2026-10-24", "2026-10-26")).toBe(2);
    expect(tageZwischen("2026-03-28", "2026-03-30")).toBe(2);
    expect(tageZwischen("2026-10-19", "2026-10-18")).toBe(-1);
    expect(tageZwischen("2026-10-19", "2026-10-19")).toBe(0);
  });
});

describe("formatIsoTag", () => {
  it("dreht ISO in deutsche Schreibweise", () => {
    expect(formatIsoTag("2026-10-19")).toBe("19.10.2026");
  });
});
