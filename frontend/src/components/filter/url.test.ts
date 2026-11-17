import { Building2 } from "lucide-react";
import { describe, expect, it } from "vitest";

import type { FilterBedingung, FilterFeld } from "./typen";
import { bedingungenAusUrl, bedingungenZuUrl } from "./url";

const beispiel: FilterBedingung[] = [
  { feld: "status", op: "ist", wert: ["neu", "in_arbeit"] },
  { feld: "titel", op: "enthaelt_nicht", wert: "Wartung & Co / 100%" },
  { feld: "faellig", op: "zwischen", wert: { von: "2026-10-01", bis: "2026-10-31" } },
  { feld: "faellig", op: "relativ", wert: { relativ: "letzte_30" } },
  { feld: "kunde", op: "leer" },
];

describe("bedingungenZuUrl / bedingungenAusUrl", () => {
  it("Hin- und Rückweg ist verlustfrei", () => {
    expect(bedingungenAusUrl(bedingungenZuUrl(beispiel))).toEqual(beispiel);
  });
  it("liest auch die bereits dekodierte Form (searchParams.get)", () => {
    expect(bedingungenAusUrl(decodeURIComponent(bedingungenZuUrl(beispiel)))).toEqual(beispiel);
  });
  it("die Ausgabe ist URL-sicher", () => {
    expect(bedingungenZuUrl(beispiel)).not.toMatch(/[\s&?#]/);
  });
  it("kaputte Eingaben ergeben []", () => {
    for (const s of ["", null, undefined, "nicht json", "%E0%A4%A", "{}", "[1,2]", '[["a"]]', "[[1,2,3]]", '[["a","unsinn","x"]]', '[["a","ist",5]]']) {
      expect(bedingungenAusUrl(s)).toEqual([]);
    }
  });
  it("verwirft nur die kaputten Einträge", () => {
    expect(bedingungenAusUrl('[["a","unsinn","x"],["b","leer"]]')).toEqual([{ feld: "b", op: "leer" }]);
  });
  it("verwirft mit Feldliste unbekannte Felder und nicht angebotene Operatoren", () => {
    const felder: FilterFeld<unknown>[] = [
      { key: "titel", label: "Titel", typ: "text", icon: Building2 },
      { key: "status", label: "Status", typ: "auswahl", icon: Building2, operatoren: ["ist"] },
    ];
    const s = bedingungenZuUrl([
      { feld: "titel", op: "enthaelt", wert: "x" },
      { feld: "titel", op: "vor", wert: "2026-01-01" },
      { feld: "status", op: "ist_nicht", wert: ["a"] },
      { feld: "status", op: "ist", wert: ["a"] },
      { feld: "gibtsnicht", op: "ist", wert: "x" },
    ]);
    expect(bedingungenAusUrl(s, felder)).toEqual([
      { feld: "titel", op: "enthaelt", wert: "x" },
      { feld: "status", op: "ist", wert: ["a"] },
    ]);
  });
});
