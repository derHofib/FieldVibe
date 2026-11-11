import { describe, expect, it } from "vitest";

import type { Kunde, Material } from "../types";
import { filtereKunden, filtereMaterial, istUnterbestand } from "./geschaeft";

const material = (teil: Partial<Material>): Material =>
  ({
    id: "1",
    bezeichnung: "Kabel NYM 3x1,5",
    artikelnummer: "K-100",
    bestand_gesamt: "10",
    mindestbestand: "5",
    lieferant_id: null,
    tag_ids: [],
    ...teil,
  }) as Material;

describe("istUnterbestand", () => {
  it("zählt Bestand gleich Mindestbestand als Unterbestand", () => {
    expect(istUnterbestand(material({ bestand_gesamt: "5" }))).toBe(true);
    expect(istUnterbestand(material({ bestand_gesamt: "6" }))).toBe(false);
  });
});

describe("filtereMaterial", () => {
  const liste = [
    material({ id: "1" }),
    material({ id: "2", bezeichnung: "Dübel", artikelnummer: null, bestand_gesamt: "1", lieferant_id: "L1", tag_ids: ["t1"] }),
  ];

  it("sucht in Bezeichnung und Artikelnummer", () => {
    expect(filtereMaterial(liste, { suche: "k-100" }).map((m) => m.id)).toEqual(["1"]);
    expect(filtereMaterial(liste, { suche: "dübel" }).map((m) => m.id)).toEqual(["2"]);
  });

  it("kombiniert Filter", () => {
    expect(filtereMaterial(liste, { nurUnterbestand: true }).map((m) => m.id)).toEqual(["2"]);
    expect(filtereMaterial(liste, { lieferantId: "L1", tagId: "t2" })).toEqual([]);
  });
});

describe("filtereKunden", () => {
  it("sucht in Name und Kundennummer", () => {
    const kunden = [
      { id: "1", name: "Müller GmbH", kundennummer: "K-001" },
      { id: "2", name: "Schmidt", kundennummer: "K-002" },
    ] as Kunde[];
    expect(filtereKunden(kunden, "mül")).toHaveLength(1);
    expect(filtereKunden(kunden, "k-002")[0].id).toBe("2");
    expect(filtereKunden(kunden, "  ")).toHaveLength(2);
  });
});
