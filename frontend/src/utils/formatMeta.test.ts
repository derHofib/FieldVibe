import { describe, expect, it } from "vitest";

import { relativeZeit, statusMetaZeile } from "./format";

const jetzt = Date.parse("2026-10-04T12:00:00Z");

describe("statusMetaZeile", () => {
  it("formt den Wechsel zu einer Meta-Zeile mit relativer Zeit", () => {
    expect(statusMetaZeile("Status: Neu → In Arbeit", "2026-10-04T10:00:00Z", jetzt)).toBe("Status → In Arbeit · vor 2 Std.");
    expect(statusMetaZeile("Status: Geplant", "2026-10-04T11:59:00Z", jetzt)).toBe("Status → Geplant · gerade eben");
  });
  it("liefert null bei der Pauschale und bei anderen Vorschauen", () => {
    expect(statusMetaZeile("Status geändert", "2026-10-04T10:00:00Z", jetzt)).toBeNull();
    expect(statusMetaZeile("Foto hinzugefügt", "2026-10-04T10:00:00Z", jetzt)).toBeNull();
    expect(statusMetaZeile(null, "2026-10-04T10:00:00Z", jetzt)).toBeNull();
  });
});

describe("relativeZeit", () => {
  it("rechnet in Min., Std. und Tage", () => {
    expect(relativeZeit("2026-10-04T11:30:00Z", jetzt)).toBe("vor 30 Min.");
    expect(relativeZeit("2026-10-02T12:00:00Z", jetzt)).toBe("vor 2 Tagen");
  });
});
