import { describe, expect, it } from "vitest";

import type { Pruefmittel } from "../types";
import { faelligkeitsStufe, filterePruefmittel } from "./pruefmittel";

const HEUTE = "2026-11-17";
const BALD = "2026-12-17";

const mittel = (teil: Partial<Pruefmittel>): Pruefmittel =>
  ({
    id: "1",
    bezeichnung: "Metrahit",
    seriennummer: "SN-1",
    zugewiesen_an: null,
    naechste_kalibrierung_am: "2027-06-01",
    status: "aktiv",
    ...teil,
  }) as Pruefmittel;

describe("faelligkeitsStufe", () => {
  it("unterscheidet überfällig, bald und ok mit Grenzen", () => {
    expect(faelligkeitsStufe("2026-11-16", HEUTE, BALD)).toBe("ueberfaellig");
    expect(faelligkeitsStufe(HEUTE, HEUTE, BALD)).toBe("bald");
    expect(faelligkeitsStufe(BALD, HEUTE, BALD)).toBe("bald");
    expect(faelligkeitsStufe("2026-12-18", HEUTE, BALD)).toBe("ok");
  });
});

describe("filterePruefmittel", () => {
  const liste = [
    mittel({ id: "1" }),
    mittel({ id: "2", bezeichnung: "Zangenmesser", seriennummer: null, naechste_kalibrierung_am: "2026-01-01", zugewiesen_an: "u1" }),
    mittel({ id: "3", naechste_kalibrierung_am: "2026-01-01", status: "defekt" }),
  ];
  const name = (id: string | null) => (id === "u1" ? "Max Müller" : "");

  it("sucht in Bezeichnung, Seriennummer und zugewiesenem Nutzer", () => {
    expect(filterePruefmittel(liste, "sn-1", "alle", HEUTE, BALD, name).map((p) => p.id)).toEqual(["1", "3"]);
    expect(filterePruefmittel(liste, "müller", "alle", HEUTE, BALD, name).map((p) => p.id)).toEqual(["2"]);
  });

  it("Fälligkeitsfilter blendet inaktive Geräte aus", () => {
    expect(filterePruefmittel(liste, "", "ueberfaellig", HEUTE, BALD, name).map((p) => p.id)).toEqual(["2"]);
    expect(filterePruefmittel(liste, "", "ok", HEUTE, BALD, name).map((p) => p.id)).toEqual(["1"]);
  });
});
