import { describe, expect, it } from "vitest";

import {
  alleMitKindern,
  berechneLayout,
  nachfahren,
  standardEingeklappt,
  STANDARD_MASSE,
  type LayoutKnoten,
} from "./layout";

const k = (id: string, parentId: string | null, typ: LayoutKnoten["typ"] = "linie"): LayoutKnoten => ({
  id,
  parentId,
  typ,
});

// GF
//  ├─ Technik ── T1, T2, T3
//  │     └─ (Stab) QM ── QM1
//  ├─ Verwaltung ── V1
//  └─ (Stab) Datenschutz
const BEISPIEL: LayoutKnoten[] = [
  k("gf", null),
  k("technik", "gf"),
  k("t1", "technik"),
  k("t2", "technik"),
  k("t3", "technik"),
  k("qm", "technik", "stabsstelle"),
  k("qm1", "qm"),
  k("verwaltung", "gf"),
  k("v1", "verwaltung"),
  k("ds", "gf", "stabsstelle"),
];

function ueberlappt(
  a: { x: number; y: number },
  b: { x: number; y: number },
  m = STANDARD_MASSE,
): boolean {
  return (
    a.x < b.x + m.knotenBreite && b.x < a.x + m.knotenBreite && a.y < b.y + m.knotenHoehe && b.y < a.y + m.knotenHoehe
  );
}

function keineUeberlappung(positionen: Map<string, { x: number; y: number }>) {
  const eintraege = [...positionen.entries()];
  for (let i = 0; i < eintraege.length; i++) {
    for (let j = i + 1; j < eintraege.length; j++) {
      expect(ueberlappt(eintraege[i][1], eintraege[j][1]), `${eintraege[i][0]} / ${eintraege[j][0]}`).toBe(false);
    }
  }
}

describe("berechneLayout", () => {
  it("ordnet Ebenen top-down und zentriert Eltern ueber ihren Linien-Kindern", () => {
    const { positionen } = berechneLayout(BEISPIEL, new Set());
    const gf = positionen.get("gf")!;
    const technik = positionen.get("technik")!;
    const t1 = positionen.get("t1")!;
    const t3 = positionen.get("t3")!;
    expect(technik.y).toBeGreaterThan(gf.y);
    expect(t1.y).toBe(positionen.get("t2")!.y);
    expect(t1.y).toBeGreaterThan(technik.y);
    // Mitte von technik = Mitte zwischen erstem und letztem Kind
    expect(technik.x).toBeCloseTo((t1.x + t3.x) / 2);
  });

  it("setzt Stabsstellen auf eine Zwischenebene seitlich neben den Anker", () => {
    const { positionen, kanten } = berechneLayout(BEISPIEL, new Set());
    const technik = positionen.get("technik")!;
    const qm = positionen.get("qm")!;
    const t1 = positionen.get("t1")!;
    expect(qm.x).toBeGreaterThan(technik.x + STANDARD_MASSE.knotenBreite - 1);
    expect(qm.y).toBeGreaterThan(technik.y);
    expect(qm.y).toBeLessThan(t1.y);
    // Unterposition der Stabsstelle liegt darunter
    expect(positionen.get("qm1")!.y).toBeGreaterThan(qm.y);
    expect(kanten.find((e) => e.ziel === "qm")?.stab).toBe(true);
    expect(kanten.find((e) => e.ziel === "t1")?.stab).toBe(false);
  });

  it("laesst im Beispielbaum keine Knoten ueberlappen", () => {
    keineUeberlappung(berechneLayout(BEISPIEL, new Set()).positionen);
  });

  it("laesst auch bei breiten Teilbaeumen mit mehreren Stabsstellen nichts ueberlappen", () => {
    const viele: LayoutKnoten[] = [k("w", null)];
    for (let i = 0; i < 4; i++) {
      viele.push(k(`b${i}`, "w"));
      viele.push(k(`bs${i}`, `b${i}`, "stabsstelle"));
      viele.push(k(`bsk${i}`, `bs${i}`));
      for (let j = 0; j < 3; j++) {
        viele.push(k(`b${i}t${j}`, `b${i}`));
        viele.push(k(`b${i}t${j}s`, `b${i}t${j}`, "stabsstelle"));
        viele.push(k(`b${i}t${j}x`, `b${i}t${j}`));
      }
    }
    viele.push(k("ws1", "w", "stabsstelle"), k("ws2", "w", "stabsstelle"));
    const { positionen } = berechneLayout(viele, new Set());
    expect(positionen.size).toBe(viele.length);
    keineUeberlappung(positionen);
  });

  it("blendet eingeklappte Teilbaeume aus, behaelt aber die Kinderzahl", () => {
    const { positionen, kanten, kinderAnzahl } = berechneLayout(BEISPIEL, new Set(["technik"]));
    expect(positionen.has("technik")).toBe(true);
    for (const id of ["t1", "t2", "t3", "qm", "qm1"]) expect(positionen.has(id)).toBe(false);
    expect(kanten.some((e) => e.quelle === "technik")).toBe(false);
    expect(kinderAnzahl.get("technik")).toBe(4);
    expect(positionen.has("v1")).toBe(true);
  });

  it("verwaltet mehrere Wurzeln nebeneinander ohne Ueberlappung", () => {
    const { positionen } = berechneLayout([k("a", null), k("a1", "a"), k("b", null), k("b1", "b")], new Set());
    keineUeberlappung(positionen);
  });

  it("ist gegen Zyklen in den Daten abgesichert", () => {
    const { positionen } = berechneLayout([k("a", "b"), k("b", "a"), k("c", null)], new Set());
    expect(positionen.has("c")).toBe(true);
  });
});

describe("Hilfsfunktionen", () => {
  it("nachfahren liefert alle Unterknoten inkl. Stabsstellen-Zweige", () => {
    expect([...nachfahren(BEISPIEL, "technik")].sort()).toEqual(["qm", "qm1", "t1", "t2", "t3"]);
    expect(nachfahren(BEISPIEL, "t1").size).toBe(0);
  });

  it("standardEingeklappt laesst 3 Ebenen offen", () => {
    const tief = [k("a", null), k("b", "a"), k("c", "b"), k("d", "c"), k("e", "d")];
    // Ebene 1-3 (a, b, c) bleiben sichtbar; c zeigt seine Kinder nicht, d (Ebene 4) ist ebenfalls zugeklappt.
    const zu = standardEingeklappt(tief, 3);
    expect([...zu].sort()).toEqual(["c", "d"]);
    const { positionen } = berechneLayout(tief, zu);
    expect([...positionen.keys()].sort()).toEqual(["a", "b", "c"]);
  });

  it("alleMitKindern ignoriert Blaetter", () => {
    expect([...alleMitKindern(BEISPIEL)].sort()).toEqual(["gf", "qm", "technik", "verwaltung"]);
  });
});
