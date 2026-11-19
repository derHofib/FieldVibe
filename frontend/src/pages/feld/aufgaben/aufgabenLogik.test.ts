// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";

import { filterAnwenden } from "../../../components/filter/auswerten";
import type { ProjektAufgabe } from "../../../types";
import {
  aufgabenFilterFelder,
  eingeklapptLesen,
  eingeklapptSchreiben,
  gruppiereAufgaben,
  gruppierungAusUrl,
  kennzahlen,
  sortiereAufgaben,
  sortierungAusUrl,
  sucheAufgaben,
} from "./aufgabenLogik";

const HEUTE = "2026-11-19";

function aufgabe(teil: Partial<ProjektAufgabe> & { id: string }): ProjektAufgabe {
  return {
    projekt_id: null,
    spalte_id: null,
    eltern_aufgabe_id: null,
    titel: teil.id,
    beschreibung: null,
    faelligkeit_am: null,
    prioritaet: "mittel",
    zugewiesen_an: null,
    erledigt_am: null,
    vorgang_id: null,
    auftrag_id: null,
    anlage_id: null,
    kunde_id: null,
    standort_id: null,
    checkliste: [],
    zusatzfelder: {},
    erstellt_von: "u",
    created_at: "2026-11-01T10:00:00Z",
    updated_at: "2026-11-01T10:00:00Z",
    ...teil,
  };
}

const A = aufgabe({ id: "a", titel: "Materialliste prüfen", faelligkeit_am: "2026-11-17", prioritaet: "hoch", projekt_id: "p1", pfad_projekt_id: "p1", pfad_projekt_name: "Neubau Kita", spalte_name: "In Arbeit", auftrag_titel: "Elektro", pfad_auftrag_id: "au1", kunde_name: "Stadt Lindenau" });
const B = aufgabe({ id: "b", titel: "Angebot nachfassen", faelligkeit_am: HEUTE, vorgang_vorgangsnummer: "V-1004", vorgang_titel: "Wallbox", kunde_name: "Familie Schneider" });
const C = aufgabe({ id: "c", titel: "Abgleich Wartung", faelligkeit_am: "2026-11-22", prioritaet: "niedrig", projekt_id: "p2", pfad_projekt_id: "p2", pfad_projekt_name: "Wartung 2026", spalte_name: "Warten" });
const D = aufgabe({ id: "d", titel: "Inventur", prioritaet: "hoch" });
const E = aufgabe({ id: "e", titel: "PV-Wartung", faelligkeit_am: "2027-03-03" });
const ALLE = [A, B, C, D, E];

describe("sucheAufgaben", () => {
  it("findet alle Wörter über Titel, Projekt, Vorgang und Kunde", () => {
    expect(sucheAufgaben(ALLE, "kita lindenau").map((a) => a.id)).toEqual(["a"]);
    expect(sucheAufgaben(ALLE, "v-1004 wallbox").map((a) => a.id)).toEqual(["b"]);
  });
  it("ignoriert Umlaute-Schreibweise und leere Suche", () => {
    expect(sucheAufgaben(ALLE, "pruefen").map((a) => a.id)).toEqual(["a"]);
    expect(sucheAufgaben(ALLE, "  ")).toBe(ALLE);
  });
  it("sucht auch in Auftrag", () => {
    expect(sucheAufgaben(ALLE, "elektro").map((a) => a.id)).toEqual(["a"]);
  });
});

describe("sortiereAufgaben", () => {
  it("Fälligkeit: ohne Termin ans Ende", () => {
    expect(sortiereAufgaben(ALLE, "faelligkeit").map((a) => a.id)).toEqual(["a", "b", "c", "e", "d"]);
  });
  it("Priorität: hoch zuerst, dann nach Titel", () => {
    expect(sortiereAufgaben(ALLE, "prioritaet").map((a) => a.id)).toEqual(["d", "a", "b", "e", "c"]);
  });
  it("Titel alphabetisch", () => {
    expect(sortiereAufgaben(ALLE, "titel").map((a) => a.titel)[0]).toBe("Abgleich Wartung");
  });
  it("zuletzt geändert und angelegt: neueste zuerst", () => {
    const alt = aufgabe({ id: "alt", updated_at: "2026-01-01T00:00:00Z", created_at: "2026-01-01T00:00:00Z" });
    const neu = aufgabe({ id: "neu", updated_at: "2026-05-01T00:00:00Z", created_at: "2026-05-01T00:00:00Z" });
    expect(sortiereAufgaben([alt, neu], "geaendert")[0].id).toBe("neu");
    expect(sortiereAufgaben([alt, neu], "angelegt")[0].id).toBe("neu");
  });
  it("verändert die Eingabe nicht", () => {
    const kopie = [...ALLE];
    sortiereAufgaben(ALLE, "titel");
    expect(ALLE).toEqual(kopie);
  });
});

describe("gruppiereAufgaben", () => {
  it("Fälligkeit in fester Reihenfolge, leere Gruppen entfallen", () => {
    const g = gruppiereAufgaben(sortiereAufgaben(ALLE, "faelligkeit"), "faelligkeit", HEUTE);
    expect(g.map((x) => x.label)).toEqual(["Überfällig", "Heute", "Diese Woche", "Später", "Ohne Termin"]);
    expect(g[0].warnung).toBe(true);
    expect(g[2].aufgaben.map((a) => a.id)).toEqual(["c"]);
  });
  it("Projekt: alphabetisch, Ohne Projekt zuletzt", () => {
    const g = gruppiereAufgaben(ALLE, "projekt", HEUTE);
    expect(g.map((x) => x.label)).toEqual(["Neubau Kita", "Wartung 2026", "Ohne Projekt"]);
    expect(g[2].aufgaben).toHaveLength(3);
  });
  it("Auftrag und Kunde mit Ohne-Gruppe am Ende", () => {
    expect(gruppiereAufgaben(ALLE, "auftrag", HEUTE).map((x) => x.label)).toEqual(["Elektro", "Ohne Auftrag"]);
    expect(gruppiereAufgaben(ALLE, "kunde", HEUTE).map((x) => x.label)).toEqual(["Familie Schneider", "Stadt Lindenau", "Ohne Kunde"]);
  });
  it("Priorität: hoch, mittel, niedrig", () => {
    expect(gruppiereAufgaben(ALLE, "prioritaet", HEUTE).map((x) => x.label)).toEqual(["Hoch", "Mittel", "Niedrig"]);
  });
  it("Quelle: Privat zuerst, dann je Kanban-Spalte", () => {
    expect(gruppiereAufgaben(ALLE, "quelle", HEUTE).map((x) => x.label)).toEqual(["Privat", "In Arbeit", "Warten"]);
  });
  it("keine: eine Gruppe ohne Label; leere Liste: keine Gruppe", () => {
    expect(gruppiereAufgaben(ALLE, "keine", HEUTE)).toEqual([{ key: "alle", label: "", aufgaben: ALLE }]);
    expect(gruppiereAufgaben([], "projekt", HEUTE)).toEqual([]);
  });
});

describe("Filter über die Felder", () => {
  const felder = aufgabenFilterFelder(ALLE, false);
  it("Quelle und Projekt", () => {
    expect(filterAnwenden(ALLE, [{ feld: "quelle", op: "ist", wert: ["privat"] }], felder).map((a) => a.id)).toEqual(["b", "d", "e"]);
    expect(filterAnwenden(ALLE, [{ feld: "projekt", op: "ist", wert: ["p1"] }], felder).map((a) => a.id)).toEqual(["a"]);
    expect(filterAnwenden(ALLE, [{ feld: "projekt", op: "leer" }], felder)).toHaveLength(3);
  });
  it("Fällig überfällig und ohne Termin", () => {
    expect(filterAnwenden(ALLE, [{ feld: "faellig", op: "relativ", wert: { relativ: "ueberfaellig" } }], felder).map((a) => a.id)).toContain("a");
    expect(filterAnwenden(ALLE, [{ feld: "faellig", op: "leer" }], felder).map((a) => a.id)).toEqual(["d"]);
  });
  it("Erledigt am nur im Erledigt-Segment", () => {
    expect(felder.some((f) => f.key === "erledigt_am")).toBe(false);
    expect(aufgabenFilterFelder(ALLE, true).some((f) => f.key === "erledigt_am")).toBe(true);
  });
  it("Optionen aus den Daten, ohne Dubletten", () => {
    const projekt = felder.find((f) => f.key === "projekt")!;
    expect(projekt.optionen?.map((o) => o.label)).toEqual(["Neubau Kita", "Wartung 2026"]);
  });
});

describe("kennzahlen", () => {
  it("zählt offen und überfällig", () => {
    expect(kennzahlen(ALLE, HEUTE)).toEqual({ offen: 5, ueberfaellig: 1 });
  });
});

describe("URL-Werte", () => {
  it("fällt bei Unbekanntem auf den Standard zurück", () => {
    expect(gruppierungAusUrl("projekt")).toBe("projekt");
    expect(gruppierungAusUrl("keine")).toBe("keine");
    expect(gruppierungAusUrl("quatsch")).toBe("faelligkeit");
    expect(gruppierungAusUrl(null)).toBe("faelligkeit");
    expect(sortierungAusUrl("titel")).toBe("titel");
    expect(sortierungAusUrl("x")).toBe("faelligkeit");
  });
});

describe("eingeklappte Gruppen", () => {
  beforeEach(() => localStorage.clear());
  it("merkt sich je Gruppierung", () => {
    eingeklapptSchreiben("projekt", ["p1"]);
    expect(eingeklapptLesen("projekt")).toEqual(["p1"]);
    expect(eingeklapptLesen("kunde")).toEqual([]);
  });
  it("übersteht kaputte Werte", () => {
    localStorage.setItem("fieldvibe-aufgaben-eingeklappt-projekt", "{kaputt");
    expect(eingeklapptLesen("projekt")).toEqual([]);
  });
});
