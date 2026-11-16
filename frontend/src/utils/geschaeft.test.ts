import { describe, expect, it } from "vitest";

import type { Kunde, Material, Partner } from "../types";
import { filtereKunden, filtereMaterial, filterePartner, istUnterbestand } from "./geschaeft";

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

describe("filterePartner", () => {
  const p = (teil: Partial<Partner>): Partner =>
    ({
      id: "1",
      name: "Firma",
      gewerk: null,
      ansprechpartner: [],
      telefon: null,
      email: null,
      adresse: null,
      aktiv: true,
      ...teil,
    }) as Partner;

  it("trifft jedes Suchfeld", () => {
    const liste = [
      p({ id: "n", name: "Alpha Bau" }),
      p({ id: "g", gewerk: "Trockenbau" }),
      p({ id: "e", email: "info@beta.de" }),
      p({ id: "t", telefon: "0171 555" }),
      p({ id: "o", adresse: { ort: "Hamburg" } as Partner["adresse"] }),
      p({ id: "z", adresse: { plz: "20095" } as Partner["adresse"] }),
      p({ id: "a", ansprechpartner: [{ id: "x", name: "Erika Mustermann" }] as Partner["ansprechpartner"] }),
    ];
    for (const [q, id] of [
      ["alpha", "n"],
      ["trocken", "g"],
      ["beta.de", "e"],
      ["555", "t"],
      ["hamburg", "o"],
      ["20095", "z"],
      ["mustermann", "a"],
    ]) {
      expect(filterePartner(liste, q, "alle").map((x) => x.id)).toEqual([id]);
    }
  });

  it("ignoriert Groß-/Kleinschreibung inkl. Umlaute und trimmt", () => {
    const liste = [p({ gewerk: "Gerüstbau" })];
    expect(filterePartner(liste, "  GERÜST ", "alle")).toHaveLength(1);
    expect(filterePartner(liste, "gerüst", "alle")).toHaveLength(1);
  });

  it("überspringt null-Felder ohne Fehler", () => {
    expect(filterePartner([p({})], "xyz", "alle")).toHaveLength(0);
  });

  it("filtert nach Status; leere Suche liefert alles nach Status", () => {
    const liste = [p({ id: "a", aktiv: true }), p({ id: "b", aktiv: false })];
    expect(filterePartner(liste, "", "aktiv").map((x) => x.id)).toEqual(["a"]);
    expect(filterePartner(liste, "", "inaktiv").map((x) => x.id)).toEqual(["b"]);
    expect(filterePartner(liste, "", "alle")).toHaveLength(2);
  });
});
