import { describe, expect, it } from "vitest";

import type { RechnungPosition } from "../types";
import { formatStunden, gruppierePositionen } from "./rechnungAbrechnung";

const pos = (id: string, gesamt: string, vorgangId: string | null): RechnungPosition => ({
  id,
  position: 1,
  beschreibung: id,
  menge: "1",
  einheit: "Stk",
  einzelpreis: gesamt,
  gesamt,
  quelle: null,
  vorgang_id: vorgangId,
});

describe("formatStunden", () => {
  it("formatiert deutsch", () => {
    expect(formatStunden("3.5")).toBe("3,50 Std");
    expect(formatStunden("0")).toBe("0,00 Std");
  });
});

describe("gruppierePositionen", () => {
  const vorgaenge = [
    { id: "v2", vorgangsnummer: "V-00002", titel: "B" },
    { id: "v1", vorgangsnummer: "V-00001", titel: "A" },
    { id: "v3", vorgangsnummer: "V-00003", titel: "leer" },
  ];

  it("gruppiert in Reihenfolge der Vorgaenge und summiert exakt", () => {
    const r = gruppierePositionen(
      [pos("a", "0.10", "v1"), pos("b", "0.20", "v1"), pos("c", "10.05", "v2"), pos("d", "5.00", null)],
      vorgaenge,
    );
    expect(r.ohneVorgang.map((p) => p.id)).toEqual(["d"]);
    expect(r.gruppen.map((g) => g.vorgang.id)).toEqual(["v2", "v1"]);
    expect(r.gruppen[1].zwischensumme).toBe("0.30");
    expect(r.gruppen[0].zwischensumme).toBe("10.05");
  });

  it("unbekannte vorgang_id faellt in die ungruppierte Liste", () => {
    const r = gruppierePositionen([pos("x", "1.00", "fremd")], vorgaenge);
    expect(r.ohneVorgang).toHaveLength(1);
    expect(r.gruppen).toHaveLength(0);
  });
});
