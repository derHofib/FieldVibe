import { describe, expect, it } from "vitest";

import {
  darfAusfuehren,
  mappingAusVorschlag,
  offenePflichtGruppen,
  schrittErreichbar,
  spalteZuweisen,
  standardAktionen,
  statusAnzahl,
  zeilenFiltern,
} from "./datenimportUtils";
import type { ImportAnalyse, ImportZeile, ImportZusammenfassung } from "./typen";

const zusammenfassung = (teil: Partial<ImportZusammenfassung>): ImportZusammenfassung => ({
  gesamt: 10,
  neu: 5,
  warnung: 1,
  dublette: 2,
  fehler: 2,
  anlegen: 6,
  aktualisieren: 0,
  ueberspringen: 2,
  ...teil,
});

describe("Zuordnung", () => {
  it("uebernimmt den Server-Vorschlag", () => {
    expect(
      mappingAusVorschlag([
        { feld: "name", spalte: 1, sicherheit: "sicher" },
        { feld: "plz", spalte: null, sicherheit: null },
      ]),
    ).toEqual({ name: 1, plz: null });
  });

  it("gibt eine Spalte beim Neuzuweisen frei (eine Spalte, ein Feld)", () => {
    const neu = spalteZuweisen({ name: 1, ort: 2 }, "plz", 2);
    expect(neu).toEqual({ name: 1, ort: null, plz: 2 });
    expect(spalteZuweisen(neu, "plz", null).plz).toBeNull();
  });

  it("meldet offene Pflichtgruppen (ODER innerhalb der Gruppe)", () => {
    const gruppen = [
      ["name", "nachname"],
      ["kundennummer", "kundenname"],
    ];
    expect(offenePflichtGruppen({ name: null, nachname: 3 }, gruppen)).toEqual([["kundennummer", "kundenname"]]);
    expect(offenePflichtGruppen({ name: 0, kundenname: 1 }, gruppen)).toEqual([]);
  });

  it("setzt die Standard-Dublettenaktionen", () => {
    expect(
      standardAktionen([{ key: "ust_idnr", label: "x", aktionen: ["ueberspringen"], standard: "ueberspringen" }]),
    ).toEqual({ ust_idnr: "ueberspringen" });
  });
});

describe("Schritt-Logik", () => {
  const analyse = {} as ImportAnalyse;
  it("Zuordnung erst nach Analyse, Probelauf erst nach gueltiger Zuordnung und Lauf", () => {
    const leer = { analyse: null, mappingGueltig: false, probelaufErfolgt: false, abgeschlossen: false };
    expect(schrittErreichbar(2, leer)).toBe(false);
    expect(schrittErreichbar(2, { ...leer, analyse })).toBe(true);
    expect(schrittErreichbar(3, { ...leer, analyse, mappingGueltig: true })).toBe(false);
    expect(schrittErreichbar(3, { ...leer, analyse, mappingGueltig: true, probelaufErfolgt: true })).toBe(true);
    expect(schrittErreichbar(4, leer)).toBe(false);
  });

  it("nach Abschluss nur noch das Ergebnis", () => {
    const fertig = { analyse, mappingGueltig: true, probelaufErfolgt: true, abgeschlossen: true };
    expect(([1, 2, 3, 4] as const).map((s) => schrittErreichbar(s, fertig))).toEqual([false, false, false, true]);
  });

  it("Ausfuehren: nichts zu schreiben oder Fehler bei 'alles oder nichts' sperren", () => {
    expect(darfAusfuehren(zusammenfassung({}), "gueltige")).toBe(true);
    expect(darfAusfuehren(zusammenfassung({}), "alles_oder_nichts")).toBe(false);
    expect(darfAusfuehren(zusammenfassung({ fehler: 0 }), "alles_oder_nichts")).toBe(true);
    expect(darfAusfuehren(zusammenfassung({ anlegen: 0 }), "gueltige")).toBe(false);
  });
});

describe("Ergebnis-Filter", () => {
  const z = (zeile: number, status: ImportZeile["status"]): ImportZeile => ({
    zeile,
    status,
    aktion: "anlegen",
    meldungen: [],
    vorschau: {},
    dublette_art: null,
    dublette_von: null,
  });
  it("filtert nach Status", () => {
    const zeilen = [z(2, "neu"), z(3, "fehler"), z(4, "dublette"), z(5, "fehler")];
    expect(zeilenFiltern(zeilen, "fehler").map((x) => x.zeile)).toEqual([3, 5]);
    expect(zeilenFiltern(zeilen, "alle")).toHaveLength(4);
    expect(statusAnzahl(zusammenfassung({}), "dublette")).toBe(2);
    expect(statusAnzahl(zusammenfassung({}), "alle")).toBe(10);
  });
});
