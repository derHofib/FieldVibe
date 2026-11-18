import { describe, expect, it } from "vitest";

import { alteVorlageUmrechnen, bedingungenZuParameter, vorgaengeLink } from "./vorgaengeFilter";

describe("bedingungenZuParameter", () => {
  it("bildet Status, Verknüpfungen, Tag und Person ab", () => {
    expect(
      bedingungenZuParameter([
        { feld: "status", op: "ist", wert: ["neu", "geplant"] },
        { feld: "kunde", op: "ist", wert: ["k1"] },
        { feld: "projekt", op: "ist", wert: ["p1"] },
        { feld: "auftrag", op: "ist", wert: ["a1"] },
        { feld: "tag", op: "enthaelt", wert: ["#eilig"] },
        { feld: "zugewiesen", op: "ist", wert: ["ich"] },
      ]),
    ).toEqual({ status: "neu,geplant", kunde_id: "k1", projekt_id: "p1", auftrag_id: "a1", tag: "eilig", nur_meine: "true" });
  });

  it("macht aus 'ist nicht' die Restmenge", () => {
    const p = bedingungenZuParameter([{ feld: "status", op: "ist_nicht", wert: ["abgerechnet", "storniert"] }]);
    expect(p.status).toBe("neu,geplant,in_arbeit,wartet_kunde,abgeschlossen");
  });

  it("rechnet vor/nach inklusiv auf von/bis um und schneidet mehrere Bedingungen", () => {
    expect(bedingungenZuParameter([{ feld: "faellig", op: "vor", wert: "2026-03-01" }])).toEqual({ faellig_bis: "2026-02-28" });
    expect(bedingungenZuParameter([{ feld: "faellig", op: "nach", wert: "2026-12-31" }])).toEqual({ faellig_von: "2027-01-01" });
    expect(
      bedingungenZuParameter([
        { feld: "faellig", op: "nach", wert: "2026-03-01" },
        { feld: "faellig", op: "zwischen", wert: { von: "2026-01-01", bis: "2026-06-30" } },
      ]),
    ).toEqual({ faellig_von: "2026-03-02", faellig_bis: "2026-06-30" });
  });

  it("löst relative Zeiträume auf", () => {
    const p = bedingungenZuParameter([{ feld: "faellig", op: "relativ", wert: { relativ: "heute" } }]);
    expect(p.faellig_von).toBe(p.faellig_bis);
    expect(p.faellig_von).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

describe("alteVorlageUmrechnen", () => {
  it("rechnet flache Schlüssel um und ignoriert sort", () => {
    expect(
      alteVorlageUmrechnen({ status: "neu,geplant", kunde_id: "k1", auftrag_id: "a1", faellig_von: "2026-01-01", faellig_bis: "2026-01-31", nur_meine: "true", sort: "prioritaet" }),
    ).toEqual([
      { feld: "status", op: "ist", wert: ["neu", "geplant"] },
      { feld: "kunde", op: "ist", wert: ["k1"] },
      { feld: "auftrag", op: "ist", wert: ["a1"] },
      { feld: "faellig", op: "zwischen", wert: { von: "2026-01-01", bis: "2026-01-31" } },
      { feld: "zugewiesen", op: "ist", wert: ["ich"] },
    ]);
  });

  it("liefert für leere Vorlagen nichts", () => {
    expect(alteVorlageUmrechnen({})).toEqual([]);
  });
});

describe("vorgaengeLink", () => {
  it("hängt die Bedingungen als f an", () => {
    const link = vorgaengeLink("/feed", [{ feld: "projekt", op: "ist", wert: ["p1"] }]);
    expect(link.startsWith("/feed?f=")).toBe(true);
    expect(decodeURIComponent(link.slice(8))).toBe('[["projekt","ist",["p1"]]]');
  });
});
