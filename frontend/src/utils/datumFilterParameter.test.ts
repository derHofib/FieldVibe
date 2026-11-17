import { describe, expect, it } from "vitest";

import { datumServerParameter, datumZuVonBis } from "./datumFilterParameter";

describe("datumZuVonBis", () => {
  it("am setzt beide Grenzen", () => {
    expect(datumZuVonBis({ feld: "z", op: "am", wert: "2026-03-10" })).toEqual({ von: "2026-03-10", bis: "2026-03-10" });
  });
  it("vor endet am Vortag, nach beginnt am Folgetag (auch über Monatsgrenzen)", () => {
    expect(datumZuVonBis({ feld: "z", op: "vor", wert: "2026-03-01" })).toEqual({ bis: "2026-02-28" });
    expect(datumZuVonBis({ feld: "z", op: "nach", wert: "2026-01-31" })).toEqual({ von: "2026-02-01" });
  });
  it("zwischen übernimmt den Bereich, leere Grenzen entfallen", () => {
    expect(datumServerParameter({ feld: "z", op: "zwischen", wert: { von: "2026-01-01" } })).toEqual({ von: "2026-01-01" });
  });
  it("relativ löst den Zeitraum auf", () => {
    const r = datumZuVonBis({ feld: "z", op: "relativ", wert: { relativ: "heute" } });
    expect(r.von).toBe(r.bis);
  });
});
