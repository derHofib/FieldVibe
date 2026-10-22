import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { istUeberfaellig } from "../config/vorgangDarstellung";
import { istRechnungUeberfaellig } from "./buchhaltung";
import { datumZuIso, heuteIso } from "./format";

// Node liest TZ zur Laufzeit neu; ohne feste Zone wuerde der Test auf einer
// UTC-CI den Fehler gar nicht zeigen.
const urspruenglicheZone = process.env.TZ;
beforeAll(() => {
  process.env.TZ = "Europe/Berlin";
});
afterEach(() => vi.useRealTimers());
afterAll(() => {
  if (urspruenglicheZone === undefined) delete process.env.TZ;
  else process.env.TZ = urspruenglicheZone;
});

function uhr(utcIso: string) {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(utcIso));
}

describe("heuteIso in Europe/Berlin", () => {
  it("Sommer: 23:30 UTC ist schon der Folgetag (MESZ, 01:30)", () => {
    uhr("2026-07-14T23:30:00Z");
    expect(heuteIso()).toBe("2026-07-15");
    expect(new Date().toISOString().slice(0, 10)).toBe("2026-07-14");
  });

  it("Winter: 23:30 UTC ist schon der Folgetag (MEZ, 00:30)", () => {
    uhr("2026-01-14T23:30:00Z");
    expect(heuteIso()).toBe("2026-01-15");
  });

  it("Winter: 22:30 UTC ist noch derselbe Tag", () => {
    uhr("2026-01-14T22:30:00Z");
    expect(heuteIso()).toBe("2026-01-14");
  });

  it("Jahreswechsel: Silvester 23:30 UTC ist Neujahr", () => {
    uhr("2026-12-31T23:30:00Z");
    expect(heuteIso()).toBe("2027-01-01");
    expect(heuteIso(-1)).toBe("2026-12-31");
  });

  it("Offset ueber die Sommerzeitumstellung bleibt kalendertaggenau", () => {
    uhr("2026-03-28T23:30:00Z");
    expect(heuteIso()).toBe("2026-03-29");
    expect(heuteIso(1)).toBe("2026-03-30");
    expect(datumZuIso(new Date(2026, 9, 25, 0, 15))).toBe("2026-10-25");
  });
});

describe("Ueberfaelligkeit nutzt den lokalen Tag", () => {
  it("Vorgang mit Frist 'heute' ist um 00:30 Ortszeit nicht ueberfaellig", () => {
    uhr("2026-07-14T22:30:00Z");
    expect(istUeberfaellig("2026-07-15")).toBe(false);
    expect(istUeberfaellig("2026-07-14")).toBe(true);
  });

  it("Rechnung faellig am Vortag ist ueberfaellig, faellig heute nicht", () => {
    uhr("2026-12-31T23:30:00Z");
    expect(istRechnungUeberfaellig({ faellig_am: "2026-12-31", status: "versendet" })).toBe(true);
    expect(istRechnungUeberfaellig({ faellig_am: "2027-01-01", status: "versendet" })).toBe(false);
  });
});

describe("Leitplanke: kein UTC-Tag fuer 'heute'", () => {
  function dateien(dir: string): string[] {
    return readdirSync(dir).flatMap((name) => {
      const pfad = join(dir, name);
      if (statSync(pfad).isDirectory()) return dateien(pfad);
      return /\.(ts|tsx)$/.test(name) && !/\.test\.(ts|tsx)$/.test(name) ? [pfad] : [];
    });
  }

  it("src enthaelt kein toISOString().slice(0, 10)", () => {
    const treffer = dateien(join(__dirname, ".."))
      .filter((pfad) =>
        readFileSync(pfad, "utf-8")
          .split("\n")
          .some((zeile) => !/^\s*(\/\/|\*|\/\*)/.test(zeile) && /toISOString\(\)\s*\.(slice|split|substring)/.test(zeile)),
      )
      // Bug-Report-Zeitstempel sind bewusst UTC-Instants, keine Kalendertage.
      .filter((pfad) => !pfad.includes("/bugreport/"));
    expect(treffer).toEqual([]);
  });
});
