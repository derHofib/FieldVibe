import { describe, expect, it } from "vitest";

import type { AbrechenbarerVorgang } from "../types";
import { formatStunden, zaehleFehlendeSaetze } from "./rechnungAbrechnung";

const v = (id: string, ohne: string, mit = "0"): AbrechenbarerVorgang => ({
  vorgang_id: id,
  vorgangsnummer: id,
  titel: "t",
  stunden_ohne_svs: ohne,
  stunden_mit_svs: mit,
});

describe("formatStunden", () => {
  it("formatiert deutsch", () => {
    expect(formatStunden("3.5")).toBe("3,50 Std");
    expect(formatStunden("0")).toBe("0,00 Std");
  });
});

describe("zaehleFehlendeSaetze", () => {
  const liste = [v("a", "2"), v("b", "1"), v("c", "0", "3"), v("d", "4")];
  it("zaehlt nur ausgewaehlte mit Stunden ohne SVS und ohne Satz", () => {
    const sel = new Set(["a", "b", "c"]);
    expect(zaehleFehlendeSaetze(liste, sel, { a: "50", b: "" })).toBe(1);
    expect(zaehleFehlendeSaetze(liste, sel, { a: "0" })).toBe(2);
    expect(zaehleFehlendeSaetze(liste, new Set(), {})).toBe(0);
  });
});
