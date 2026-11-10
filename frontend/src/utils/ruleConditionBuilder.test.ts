import { describe, expect, it } from "vitest";

import { describeCondition, newClause, parseCondition, serializeCondition, type ParsedCondition } from "./ruleConditionBuilder";

describe("serializeCondition / parseCondition round-trip", () => {
  it("keine Klauseln -> Literal true", () => {
    const parsed: ParsedCondition = { combinator: "and", clauses: [] };
    expect(serializeCondition(parsed)).toBe(true);
    expect(parseCondition(true)).toEqual(parsed);
  });

  it("eine Klausel ohne Verknuepfungs-Wrapper", () => {
    const clause = { ...newClause("leistungstyp"), operator: "==" as const, value: "wartung" };
    const parsed: ParsedCondition = { combinator: "and", clauses: [clause] };
    const json = serializeCondition(parsed);
    expect(json).toEqual({ "==": [{ var: "leistungstyp" }, "wartung"] });
    expect(parseCondition(json)).toEqual(parsed);
  });

  it("mehrere Klauseln mit UND", () => {
    const parsed: ParsedCondition = {
      combinator: "and",
      clauses: [
        { field: "leistungstyp", operator: "==", value: "wartung", values: [] },
        { field: "zustand", operator: "!=", value: "gut", values: [] },
      ],
    };
    const json = serializeCondition(parsed);
    expect(json).toEqual({
      and: [
        { "==": [{ var: "leistungstyp" }, "wartung"] },
        { "!=": [{ var: "zustand" }, "gut"] },
      ],
    });
    expect(parseCondition(json)).toEqual(parsed);
  });

  it("mehrere Klauseln mit ODER", () => {
    const parsed: ParsedCondition = {
      combinator: "or",
      clauses: [
        { field: "status", operator: "==", value: "offen", values: [] },
        { field: "status", operator: "==", value: "in_bearbeitung", values: [] },
      ],
    };
    expect(parseCondition(serializeCondition(parsed))).toEqual(parsed);
  });

  it("'in' Operator -- Feld ist einer von mehreren Werten", () => {
    const parsed: ParsedCondition = {
      combinator: "and",
      clauses: [{ field: "status", operator: "in", value: "", values: ["offen", "in_bearbeitung"] }],
    };
    const json = serializeCondition(parsed);
    expect(json).toEqual({ in: [{ var: "status" }, ["offen", "in_bearbeitung"]] });
    expect(parseCondition(json)).toEqual(parsed);
  });

  it("'contains' Operator -- Mehrfachauswahl-Feld enthaelt Wert", () => {
    const parsed: ParsedCondition = {
      combinator: "and",
      clauses: [{ field: "maengel_typen", operator: "contains", value: "elektrik", values: [] }],
    };
    const json = serializeCondition(parsed);
    expect(json).toEqual({ in: ["elektrik", { var: "maengel_typen" }] });
    expect(parseCondition(json)).toEqual(parsed);
  });

  it("numerische Vergleiche", () => {
    const parsed: ParsedCondition = {
      combinator: "and",
      clauses: [{ field: "temperatur", operator: ">", value: 80, values: [] }],
    };
    expect(parseCondition(serializeCondition(parsed))).toEqual(parsed);
  });

  it("nicht darstellbare Bedingungen liefern null (Fallback auf JSON-Modus)", () => {
    expect(parseCondition({ "!": [{ "==": [{ var: "a" }, 1] }] })).toBeNull();
    expect(parseCondition({ and: [{ or: [{ "==": [{ var: "a" }, 1] }] }] })).toBeNull();
    expect(parseCondition({ "==": [{ var: "a" }, { var: "b" }] })).toBeNull();
    expect(parseCondition(false)).toBeNull();
  });
});

describe("describeCondition", () => {
  const label = (key: string) => ({ leistungstyp: "Leistungstyp", zustand: "Zustand" })[key] ?? key;

  it("Literal true -> 'immer'", () => {
    expect(describeCondition(true, label)).toBe("immer");
  });

  it("einzelne Klausel", () => {
    expect(describeCondition({ "==": [{ var: "leistungstyp" }, "wartung"] }, label)).toBe("Leistungstyp ist wartung");
  });

  it("mehrere Klauseln mit UND", () => {
    const condition = {
      and: [
        { "==": [{ var: "leistungstyp" }, "wartung"] },
        { "!=": [{ var: "zustand" }, "gut"] },
      ],
    };
    expect(describeCondition(condition, label)).toBe("Leistungstyp ist wartung UND Zustand ist nicht gut");
  });

  it("boolesche Werte werden als Ja/Nein angezeigt", () => {
    expect(describeCondition({ "==": [{ var: "aktiv" }, true] }, label)).toBe("aktiv ist Ja");
    expect(describeCondition({ "==": [{ var: "aktiv" }, false] }, label)).toBe("aktiv ist Nein");
  });

  it("nicht darstellbare Bedingung faellt auf JSON zurueck", () => {
    const condition = { "!": [{ "==": [{ var: "a" }, 1] }] };
    expect(describeCondition(condition, label)).toBe(JSON.stringify(condition));
  });
});
