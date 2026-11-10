import { describe, expect, it } from "vitest";

import { parseFormel, serializeFormel, type ParsedFormel } from "./ruleFormulaBuilder";

describe("serializeFormel / parseFormel round-trip", () => {
  it("kein Wert -> leere Termliste", () => {
    expect(parseFormel(null)).toEqual({ terme: [], operatoren: [] });
    expect(parseFormel(undefined)).toEqual({ terme: [], operatoren: [] });
  });

  it("ein einzelner Feld-Term ohne Operator", () => {
    const parsed: ParsedFormel = { terme: [{ art: "feld", wert: "menge" }], operatoren: [] };
    const json = serializeFormel(parsed);
    expect(json).toEqual({ var: "menge" });
    expect(parseFormel(json)).toEqual(parsed);
  });

  it("ein einzelner Zahl-Term ohne Operator", () => {
    const parsed: ParsedFormel = { terme: [{ art: "zahl", wert: "1.19" }], operatoren: [] };
    expect(serializeFormel(parsed)).toBe(1.19);
    expect(parseFormel(1.19)).toEqual({ terme: [{ art: "zahl", wert: "1.19" }], operatoren: [] });
  });

  it("zwei Terme: Feld + Feld", () => {
    const parsed: ParsedFormel = {
      terme: [
        { art: "feld", wert: "laenge" },
        { art: "feld", wert: "breite" },
      ],
      operatoren: ["*"],
    };
    const json = serializeFormel(parsed);
    expect(json).toEqual({ "*": [{ var: "laenge" }, { var: "breite" }] });
    expect(parseFormel(json)).toEqual(parsed);
  });

  it("drei Terme, linksassoziativ: (a + b) * c", () => {
    const parsed: ParsedFormel = {
      terme: [
        { art: "feld", wert: "a" },
        { art: "feld", wert: "b" },
        { art: "feld", wert: "c" },
      ],
      operatoren: ["+", "*"],
    };
    const json = serializeFormel(parsed);
    expect(json).toEqual({ "*": [{ "+": [{ var: "a" }, { var: "b" }] }, { var: "c" }] });
    expect(parseFormel(json)).toEqual(parsed);
  });

  it("Mischung aus Feld- und Zahl-Termen", () => {
    const parsed: ParsedFormel = {
      terme: [
        { art: "feld", wert: "menge" },
        { art: "zahl", wert: "1.19" },
      ],
      operatoren: ["*"],
    };
    const json = serializeFormel(parsed);
    expect(json).toEqual({ "*": [{ var: "menge" }, 1.19] });
    expect(parseFormel(json)).toEqual(parsed);
  });

  it("nicht darstellbare Formel liefert null (Fallback auf JSON-Modus)", () => {
    expect(parseFormel({ "==": [{ var: "a" }, 1] })).toBeNull();
    expect(parseFormel({ "+": [{ var: "a" }, { "==": [{ var: "b" }, 1] }] })).toBeNull();
    expect(parseFormel("ueberschritten")).toBeNull();
    expect(parseFormel(true)).toBeNull();
  });
});
