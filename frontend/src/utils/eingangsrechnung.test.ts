import { describe, expect, it } from "vitest";

import type { Eingangsrechnung } from "../types";
import { eingangsKennzahlen } from "./eingangsrechnung";

const heute = new Date(2026, 10, 19, 14, 30); // 19.11.2026

const rechnung = (teil: Partial<Eingangsrechnung>): Eingangsrechnung =>
  ({
    status: "offen",
    offener_betrag: "0",
    betrag_brutto: "0",
    faellig_am: null,
    skonto_frist: null,
    skonto_betrag: null,
    bezahlt_am: null,
    ...teil,
  }) as Eingangsrechnung;

describe("eingangsKennzahlen", () => {
  it("liefert für eine leere Liste lauter Nullen", () => {
    const k = eingangsKennzahlen([], heute);
    expect(k.offen).toEqual({ summe: 0, anzahl: 0 });
    expect(k.ueberfaellig.anzahl).toBe(0);
    expect(k.skonto.anzahl).toBe(0);
    expect(k.bezahltImMonat.anzahl).toBe(0);
  });

  it("summiert offene Beträge nur für Status offen", () => {
    const k = eingangsKennzahlen(
      [
        rechnung({ offener_betrag: "100.50" }),
        rechnung({ offener_betrag: "20" }),
        rechnung({ status: "entwurf", offener_betrag: "999" }),
        rechnung({ status: "storniert", offener_betrag: "999" }),
      ],
      heute,
    );
    expect(k.offen).toEqual({ summe: 120.5, anzahl: 2 });
  });

  it("zählt überfällig nur vor heute und nennt die älteste in Tagen", () => {
    const k = eingangsKennzahlen(
      [
        rechnung({ offener_betrag: "10", faellig_am: "2026-11-18" }),
        rechnung({ offener_betrag: "20", faellig_am: "2026-11-09" }),
        rechnung({ offener_betrag: "40", faellig_am: "2026-11-19" }),
        rechnung({ status: "bezahlt", offener_betrag: "0", faellig_am: "2026-01-01" }),
      ],
      heute,
    );
    expect(k.ueberfaellig).toEqual({ summe: 30, anzahl: 2, aeltesteTage: 10 });
  });

  it("Skonto: Frist von heute bis heute+7 inklusive", () => {
    const k = eingangsKennzahlen(
      [
        rechnung({ skonto_frist: "2026-11-19", skonto_betrag: "3" }),
        rechnung({ skonto_frist: "2026-11-26", skonto_betrag: "4.5" }),
        rechnung({ skonto_frist: "2026-11-27", skonto_betrag: "100" }),
        rechnung({ skonto_frist: "2026-11-18", skonto_betrag: "100" }),
        rechnung({ status: "bezahlt", skonto_frist: "2026-11-20", skonto_betrag: "100" }),
      ],
      heute,
    );
    expect(k.skonto).toEqual({ anzahl: 2, ersparnis: 7.5 });
  });

  it("Bezahlt im laufenden Monat: Summe brutto, andere Monate zählen nicht", () => {
    const k = eingangsKennzahlen(
      [
        rechnung({ status: "bezahlt", bezahlt_am: "2026-11-02T08:00:00Z", betrag_brutto: "119" }),
        rechnung({ status: "bezahlt", bezahlt_am: "2026-11-30", betrag_brutto: "81" }),
        rechnung({ status: "bezahlt", bezahlt_am: "2026-10-31", betrag_brutto: "500" }),
        rechnung({ status: "bezahlt", bezahlt_am: null, betrag_brutto: "500" }),
      ],
      heute,
    );
    expect(k.bezahltImMonat).toEqual({ summe: 200, anzahl: 2 });
  });
});
