import { describe, expect, it } from "vitest";

import {
  FEHLER_STATUS,
  FEHLER_STATUS_LABEL,
  FEHLER_STATUS_TOKEN,
  SCHWEREGRADE,
  SCHWEREGRAD_KLASSE,
  istDringend,
  netzwerkFehlgeschlagen,
  relativeZeit,
} from "../darstellung";

describe("Status-Mapping", () => {
  it("deckt alle sechs Status mit Label und Token ab", () => {
    for (const s of FEHLER_STATUS) {
      expect(FEHLER_STATUS_LABEL[s]).toBeTruthy();
      expect(FEHLER_STATUS_TOKEN[s]).toBeTruthy();
    }
    expect(FEHLER_STATUS_TOKEN.neu).toBe("neu");
    expect(FEHLER_STATUS_TOKEN.in_arbeit).toBe("arbeit");
    expect(FEHLER_STATUS_TOKEN.behoben).toBe("erledigt");
  });
});

describe("Schweregrad-Mapping", () => {
  it("blockierend rot, hoch orange, niedrig grau, mittel neutral", () => {
    expect(SCHWEREGRAD_KLASSE.blockierend).toContain("st-fehlt");
    expect(SCHWEREGRAD_KLASSE.hoch).toContain("st-arbeit");
    expect(SCHWEREGRAD_KLASSE.niedrig).toContain("st-geplant");
    expect(SCHWEREGRAD_KLASSE.mittel).toContain("bg-fill2");
    expect(SCHWEREGRADE.every((s) => SCHWEREGRAD_KLASSE[s])).toBe(true);
  });

  it("hebt nur blockierend und hoch hervor", () => {
    expect(SCHWEREGRADE.filter(istDringend)).toEqual(["hoch", "blockierend"]);
  });
});

describe("netzwerkFehlgeschlagen", () => {
  it("erkennt status >= 400 und gesetztes fehler-Feld", () => {
    expect(netzwerkFehlgeschlagen({ status: 200 })).toBe(false);
    expect(netzwerkFehlgeschlagen({ status: 399 })).toBe(false);
    expect(netzwerkFehlgeschlagen({ status: 400 })).toBe(true);
    expect(netzwerkFehlgeschlagen({ status: 500 })).toBe(true);
    expect(netzwerkFehlgeschlagen({ status: 0, fehler: "Failed to fetch" })).toBe(true);
  });
});

describe("relativeZeit", () => {
  const jetzt = new Date("2026-10-04T12:00:00Z").getTime();
  it("formatiert Minuten, Stunden und Tage", () => {
    expect(relativeZeit("2026-10-04T11:59:30Z", jetzt)).toBe("gerade eben");
    expect(relativeZeit("2026-10-04T11:30:00Z", jetzt)).toBe("vor 30 Min.");
    expect(relativeZeit("2026-10-04T10:00:00Z", jetzt)).toBe("vor 2 Std.");
    expect(relativeZeit("2026-10-03T12:00:00Z", jetzt)).toBe("vor 1 Tag");
    expect(relativeZeit("2026-10-01T12:00:00Z", jetzt)).toBe("vor 3 Tagen");
  });
});
