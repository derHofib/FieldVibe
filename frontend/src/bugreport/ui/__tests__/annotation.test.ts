import { describe, expect, it } from "vitest";

import {
  clientZuBild,
  formHinzufuegen,
  istSinnvoll,
  normalisiereRechteck,
  pfeilSpitze,
  rueckgaengig,
  strichBreite,
  zuruecksetzen,
  type Form,
} from "../annotation";

const rechteck: Form = { typ: "rechteck", von: { x: 0, y: 0 }, nach: { x: 10, y: 10 } };
const schwaerzen: Form = { typ: "schwaerzen", von: { x: 5, y: 5 }, nach: { x: 50, y: 20 } };

describe("Formenliste", () => {
  it("fügt hinzu, ohne die Eingabe zu verändern", () => {
    const leer: Form[] = [];
    const neu = formHinzufuegen(leer, rechteck);
    expect(neu).toEqual([rechteck]);
    expect(leer).toEqual([]);
  });

  it("Undo entfernt nur die letzte Form, auf leerer Liste ist es ein No-op", () => {
    const liste = formHinzufuegen(formHinzufuegen([], rechteck), schwaerzen);
    expect(rueckgaengig(liste)).toEqual([rechteck]);
    expect(rueckgaengig([])).toEqual([]);
    expect(liste).toHaveLength(2);
  });

  it("zuruecksetzen liefert eine leere Liste", () => {
    expect(zuruecksetzen()).toEqual([]);
  });
});

describe("clientZuBild", () => {
  const rect = { left: 100, top: 50, width: 400, height: 200 };

  it("rechnet auf Bildpixel um (Bild 1600x800 in 400x200 Container)", () => {
    expect(clientZuBild(300, 150, rect, 1600, 800)).toEqual({ x: 800, y: 400 });
  });

  it("begrenzt auf die Bildfläche", () => {
    expect(clientZuBild(0, 0, rect, 1600, 800)).toEqual({ x: 0, y: 0 });
    expect(clientZuBild(9999, 9999, rect, 1600, 800)).toEqual({ x: 1600, y: 800 });
  });

  it("überlebt ein Rechteck der Größe 0", () => {
    expect(clientZuBild(1, 1, { left: 0, top: 0, width: 0, height: 0 }, 100, 100)).toEqual({ x: 0, y: 0 });
  });
});

describe("Geometrie", () => {
  it("normalisiert Rechtecke unabhängig von der Ziehrichtung", () => {
    expect(normalisiereRechteck({ x: 10, y: 20 }, { x: 4, y: 8 })).toEqual({ x: 4, y: 8, breite: 6, hoehe: 12 });
  });

  it("verwirft Antippen ohne Ziehen und leeren Text", () => {
    expect(istSinnvoll({ typ: "rechteck", von: { x: 1, y: 1 }, nach: { x: 2, y: 2 } })).toBe(false);
    expect(istSinnvoll(rechteck)).toBe(true);
    expect(istSinnvoll({ typ: "freihand", punkte: [{ x: 0, y: 0 }] })).toBe(false);
    expect(istSinnvoll({ typ: "text", pos: { x: 0, y: 0 }, text: "  " })).toBe(false);
  });

  it("Pfeilspitze liegt symmetrisch hinter der Spitze", () => {
    const [a, b] = pfeilSpitze({ x: 0, y: 0 }, { x: 100, y: 0 }, 10);
    expect(a.x).toBeCloseTo(b.x);
    expect(a.x).toBeLessThan(100);
    expect(a.y).toBeCloseTo(-b.y);
  });

  it("Strichbreite skaliert mit der Bildbreite, mindestens 3", () => {
    expect(strichBreite(100)).toBe(3);
    expect(strichBreite(3000)).toBe(10);
  });
});
