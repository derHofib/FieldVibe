import { describe, expect, it } from "vitest";

import { rechnungAnOptionen } from "./rechnungAn";

describe("rechnungAnOptionen", () => {
  const hv = { id: "hv", name: "Hausverwaltung Rheinblick" };
  const weg = { id: "weg", name: "WEG Moselstraße 14" };
  const alle = [hv, weg, { id: "x", name: "Müller GmbH" }];

  it("beginnt mit dem Auftraggeber, dann die verwalteten Kunden, dann alle übrigen", () => {
    const optionen = rechnungAnOptionen(hv, [weg], alle);
    expect(optionen.map((o) => o.value)).toEqual(["", "weg", "x"]);
    expect(optionen[0].label).toBe("Auftraggeber (Hausverwaltung Rheinblick)");
    expect(optionen[1].sublabel).toBe("Verwaltet von Hausverwaltung Rheinblick");
  });

  it("führt weder den Auftraggeber noch verwaltete Kunden doppelt auf", () => {
    const optionen = rechnungAnOptionen(hv, [weg], alle);
    expect(optionen.filter((o) => o.value === "weg")).toHaveLength(1);
    expect(optionen.some((o) => o.value === "hv")).toBe(false);
  });

  it("funktioniert ohne verwaltete Kunden und ohne bekannten Auftraggeber", () => {
    expect(rechnungAnOptionen(null, [], [weg]).map((o) => o.label)).toEqual(["Auftraggeber", "WEG Moselstraße 14"]);
  });
});
