import { describe, expect, it } from "vitest";

import type { Position } from "../../types/organigramm";
import { csvDateiname, csvFeld, positionenCsv } from "./export";
import {
  filtere,
  KEIN_FILTER,
  listenZeilen,
  sortiereZeilen,
  type PositionsFilter,
} from "./liste";

const basis = (id: string, parent: string | null, titel: string, extra: Partial<Position> = {}): Position => ({
  id,
  parent_id: parent,
  titel,
  typ: "linie",
  status: "vakant",
  geplant: false,
  soll_besetzung: 1,
  ist_besetzung: 0,
  besetzungen: [],
  org_einheit: null,
  account_typ: null,
  ...extra,
});

const POSITIONEN: Position[] = [
  basis("gf", null, "Geschäftsführung", {
    status: "besetzt",
    ist_besetzung: 1,
    besetzungen: [{ id: "b", user_id: "u", name: "Max; \"Chef\" Muster", art: "regulaer", gueltig_von: "2026-01-01T00:00:00Z", gueltig_bis: null }],
  }),
  basis("ds", "gf", "Datenschutz", { typ: "stabsstelle", org_einheit: { id: "e1", name: "Stab", typ: "bereich" } }),
  basis("tech", "gf", "Technik", { org_einheit: { id: "e2", name: "Technik", typ: "bereich" }, account_typ: { id: "t", name: "Bereichsleiter" }, soll_besetzung: 2 }),
  basis("t1", "tech", "=Monteur", { status: "geplant", geplant: true }),
];

describe("CSV-Export", () => {
  it("maskiert Semikolon, Anfuehrungszeichen und Formel-Praefixe", () => {
    expect(csvFeld("a;b")).toBe('"a;b"');
    expect(csvFeld('sag "hi"')).toBe('"sag ""hi"""');
    expect(csvFeld("=SUMME(A1)")).toBe("'=SUMME(A1)");
    expect(csvFeld(null)).toBe("");
    expect(csvFeld(3)).toBe("3");
  });

  it("schreibt Kopfzeile und eine Zeile je Position in Baumreihenfolge", () => {
    const zeilen = positionenCsv(listenZeilen(POSITIONEN)).split("\r\n");
    expect(zeilen[0]).toBe("Ebene;Pfad;Titel;Typ;Organisationseinheit;Account-Typ;Status;Soll;Ist;Besetzung");
    expect(zeilen).toHaveLength(5);
    // Linien-Kinder vor Stabsstellen, Unterposition direkt unter ihrem Eltern
    expect(zeilen.map((z) => z.split(";")[2])).toEqual(["Titel", "Geschäftsführung", "Technik", "'=Monteur", "Datenschutz"]);
    expect(zeilen[1]).toContain('"Max; ""Chef"" Muster"');
    expect(zeilen[3]).toContain("Geschäftsführung / Technik / =Monteur");
    expect(zeilen[3]).toContain("Platzhalter");
  });

  it("laesst Kontextknoten aus", () => {
    const mitKontext: Position[] = [{ id: "k", parent_id: null, titel: "Pfad", typ: "linie", kontext: true }, basis("x", "k", "Sichtbar")];
    const zeilen = positionenCsv(listenZeilen(mitKontext)).split("\r\n");
    expect(zeilen).toHaveLength(2);
  });

  it("benennt die Datei mit Datum", () => {
    expect(csvDateiname(new Date("2026-10-05T12:00:00Z"))).toBe("organigramm-2026-10-05.csv");
  });
});

describe("Liste: Sortierung und Filter", () => {
  it("rueckt nach Tiefe ein und sortiert nach Spalte", () => {
    const zeilen = listenZeilen(POSITIONEN);
    expect(zeilen.map((z) => z.tiefe)).toEqual([0, 1, 2, 1]);
    const nachTitel = sortiereZeilen(zeilen, "titel", "auf").map((z) => z.position.titel);
    expect(nachTitel).toEqual(["=Monteur", "Datenschutz", "Geschäftsführung", "Technik"]);
    expect(sortiereZeilen(zeilen, "titel", "ab")[0].position.titel).toBe("Technik");
  });

  it("filtert nach Status und Org-Einheit und behaelt den Pfad der Treffer", () => {
    const status: PositionsFilter = { ...KEIN_FILTER, status: "geplant" };
    const r = filtere(POSITIONEN, status);
    expect([...r.treffer]).toEqual(["t1"]);
    expect([...r.sichtbar].sort()).toEqual(["gf", "t1", "tech"]);

    const einheit = filtere(POSITIONEN, { ...KEIN_FILTER, orgEinheitId: "e1" });
    expect([...einheit.treffer]).toEqual(["ds"]);
  });

  it("sucht in Titel, Einheit, Typ und Besetzung", () => {
    expect([...filtere(POSITIONEN, { ...KEIN_FILTER, suche: "bereichsleiter" }).treffer]).toEqual(["tech"]);
    expect([...filtere(POSITIONEN, { ...KEIN_FILTER, suche: "chef" }).treffer]).toEqual(["gf"]);
  });

  it("zeigt ohne Filter alles", () => {
    expect(filtere(POSITIONEN, KEIN_FILTER).sichtbar.size).toBe(4);
  });
});
