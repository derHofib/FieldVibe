import { Building2 } from "lucide-react";
import { describe, expect, it } from "vitest";

import {
  auswahlKomplement,
  bedingungErfuellt,
  bedingungenGleich,
  filterAnwenden,
  normalisiere,
  parseDeutscheZahl,
  pillenTeile,
  sucheAnwenden,
  zeitraumAufloesen,
  zuServerParametern,
} from "./auswerten";
import type { FilterBedingung, FilterFeld } from "./typen";

// Mittwoch, 18.11.2026
const HEUTE = new Date(2026, 10, 18, 14, 30);

describe("normalisiere", () => {
  it("bringt Umlaute, ß, Großschreibung und Akzente auf eine Form", () => {
    expect(normalisiere("  Müller ")).toBe("mueller");
    expect(normalisiere("Mueller")).toBe("mueller");
    expect(normalisiere("Straße")).toBe(normalisiere("STRASSE"));
    expect(normalisiere("Café")).toBe("cafe");
  });
});

describe("parseDeutscheZahl", () => {
  it("liest deutsches Format", () => {
    expect(parseDeutscheZahl("1.000,50")).toBe(1000.5);
    expect(parseDeutscheZahl("12 €")).toBe(12);
    expect(parseDeutscheZahl("-3,5")).toBe(-3.5);
    expect(parseDeutscheZahl("abc")).toBeNull();
    expect(parseDeutscheZahl("")).toBeNull();
  });
});

describe("bedingungErfuellt: text", () => {
  const t = (op: FilterBedingung["op"], wert?: string) => ({ feld: "x", op, wert });
  it.each([
    ["enthaelt", "wart", "Wartung Frühjahr", true],
    ["enthaelt", "xyz", "Wartung", false],
    ["enthaelt_nicht", "angebot", "Wartung", true],
    ["enthaelt_nicht", "wart", "Wartung", false],
    ["ist", "wartung", "Wartung", true],
    ["ist", "wart", "Wartung", false],
    ["ist_nicht", "wart", "Wartung", true],
    ["ist_nicht", "WARTUNG", "Wartung", false],
    ["beginnt_mit", "war", "Wartung", true],
    ["beginnt_mit", "tung", "Wartung", false],
    ["endet_mit", "tung", "Wartung", true],
    ["endet_mit", "war", "Wartung", false],
  ] as const)("%s '%s' auf '%s' = %s", (op, wert, zeile, erwartet) => {
    expect(bedingungErfuellt(zeile, t(op, wert), "text", HEUTE)).toBe(erwartet);
  });
  it("findet ä über ae und umgekehrt", () => {
    expect(bedingungErfuellt("Zählerschrank", t("enthaelt", "zaehler"), "text")).toBe(true);
    expect(bedingungErfuellt("Zaehlerschrank", t("enthaelt", "zähler"), "text")).toBe(true);
  });
  it("leer / nicht_leer", () => {
    expect(bedingungErfuellt("", t("leer"), "text")).toBe(true);
    expect(bedingungErfuellt(null, t("leer"), "text")).toBe(true);
    expect(bedingungErfuellt("x", t("leer"), "text")).toBe(false);
    expect(bedingungErfuellt("x", t("nicht_leer"), "text")).toBe(true);
    expect(bedingungErfuellt(undefined, t("nicht_leer"), "text")).toBe(false);
  });
});

describe("bedingungErfuellt: Auswahl, Verknüpfung, Person, Liste, Ja/Nein", () => {
  for (const typ of ["auswahl", "verknuepfung", "person"] as const) {
    it(`${typ}: ist / ist_nicht mit Mehrfachwerten`, () => {
      const ist = { feld: "x", op: "ist" as const, wert: ["a", "b"] };
      const nicht = { feld: "x", op: "ist_nicht" as const, wert: ["a", "b"] };
      expect(bedingungErfuellt("a", ist, typ)).toBe(true);
      expect(bedingungErfuellt("c", ist, typ)).toBe(false);
      expect(bedingungErfuellt("c", nicht, typ)).toBe(true);
      expect(bedingungErfuellt("b", nicht, typ)).toBe(false);
    });
  }
  it("verknuepfung/person: leer und nicht_leer", () => {
    expect(bedingungErfuellt(null, { feld: "x", op: "leer" }, "person")).toBe(true);
    expect(bedingungErfuellt("u1", { feld: "x", op: "nicht_leer" }, "verknuepfung")).toBe(true);
    expect(bedingungErfuellt("u1", { feld: "x", op: "leer" }, "person")).toBe(false);
  });
  it("liste: enthaelt = mindestens einer, enthaelt_nicht = keiner", () => {
    const ent = { feld: "x", op: "enthaelt" as const, wert: ["pv", "heizung"] };
    const entNicht = { feld: "x", op: "enthaelt_nicht" as const, wert: ["pv"] };
    expect(bedingungErfuellt(["pv", "x"], ent, "liste")).toBe(true);
    expect(bedingungErfuellt(["x"], ent, "liste")).toBe(false);
    expect(bedingungErfuellt(["x"], entNicht, "liste")).toBe(true);
    expect(bedingungErfuellt(["pv"], entNicht, "liste")).toBe(false);
    expect(bedingungErfuellt([], { feld: "x", op: "leer" }, "liste")).toBe(true);
    expect(bedingungErfuellt(["pv"], { feld: "x", op: "leer" }, "liste")).toBe(false);
  });
  it("janein", () => {
    expect(bedingungErfuellt(true, { feld: "x", op: "ist", wert: "ja" }, "janein")).toBe(true);
    expect(bedingungErfuellt(false, { feld: "x", op: "ist", wert: "ja" }, "janein")).toBe(false);
    expect(bedingungErfuellt(false, { feld: "x", op: "ist", wert: "nein" }, "janein")).toBe(true);
    expect(bedingungErfuellt(true, { feld: "x", op: "ist", wert: "nein" }, "janein")).toBe(false);
  });
});

describe("bedingungErfuellt: Zahl und Betrag", () => {
  const z = (op: FilterBedingung["op"], wert: FilterBedingung["wert"]) => ({ feld: "x", op, wert });
  it.each([
    ["gleich", "1.000,50", 1000.5, true],
    ["gleich", "1.000,50", 1000, false],
    ["ungleich", "5", 4, true],
    ["ungleich", "5", 5, false],
    ["gt", "5", 6, true],
    ["gt", "5", 5, false],
    ["gte", "5", 5, true],
    ["gte", "5", 4, false],
    ["lt", "5", 4, true],
    ["lt", "5", 5, false],
    ["lte", "5", 5, true],
    ["lte", "5", 6, false],
  ] as const)("%s %s auf %s = %s", (op, wert, zeile, erwartet) => {
    for (const typ of ["zahl", "betrag"] as const) expect(bedingungErfuellt(zeile, z(op, wert), typ)).toBe(erwartet);
  });
  it("zwischen (inklusive, auch einseitig) und leer", () => {
    const b = z("zwischen", { von: "100", bis: "1.000" });
    expect(bedingungErfuellt(100, b, "betrag")).toBe(true);
    expect(bedingungErfuellt(1000, b, "betrag")).toBe(true);
    expect(bedingungErfuellt(1000.01, b, "betrag")).toBe(false);
    expect(bedingungErfuellt(99, b, "betrag")).toBe(false);
    expect(bedingungErfuellt(5000, z("zwischen", { von: "100" }), "zahl")).toBe(true);
    expect(bedingungErfuellt(null, { feld: "x", op: "leer" }, "zahl")).toBe(true);
    expect(bedingungErfuellt(0, { feld: "x", op: "leer" }, "zahl")).toBe(false);
  });
});

describe("bedingungErfuellt: Datum", () => {
  const d = (op: FilterBedingung["op"], wert: FilterBedingung["wert"]) => ({ feld: "x", op, wert });
  it("am / vor / nach tagesgenau, auch mit Datetime-ISO", () => {
    expect(bedingungErfuellt("2026-11-18", d("am", "2026-11-18"), "datum")).toBe(true);
    expect(bedingungErfuellt("2026-11-19", d("am", "2026-11-18"), "datum")).toBe(false);
    expect(bedingungErfuellt(new Date(2026, 10, 18, 23, 59).toISOString(), d("am", "2026-11-18"), "datum")).toBe(true);
    expect(bedingungErfuellt("2026-11-17", d("vor", "2026-11-18"), "datum")).toBe(true);
    expect(bedingungErfuellt("2026-11-18", d("vor", "2026-11-18"), "datum")).toBe(false);
    expect(bedingungErfuellt("2026-11-19", d("nach", "2026-11-18"), "datum")).toBe(true);
    expect(bedingungErfuellt("2026-11-18", d("nach", "2026-11-18"), "datum")).toBe(false);
  });
  it("zwischen inklusive", () => {
    const b = d("zwischen", { von: "2026-10-01", bis: "2026-10-31" });
    expect(bedingungErfuellt("2026-10-01", b, "datum")).toBe(true);
    expect(bedingungErfuellt("2026-10-31", b, "datum")).toBe(true);
    expect(bedingungErfuellt("2026-11-01", b, "datum")).toBe(false);
  });
  it("relativ mit festem heute", () => {
    expect(bedingungErfuellt("2026-11-16", d("relativ", { relativ: "woche" }), "datum", HEUTE)).toBe(true);
    expect(bedingungErfuellt("2026-11-23", d("relativ", { relativ: "woche" }), "datum", HEUTE)).toBe(false);
    expect(bedingungErfuellt("2026-11-17", d("relativ", { relativ: "ueberfaellig" }), "datum", HEUTE)).toBe(true);
    expect(bedingungErfuellt("2026-11-18", d("relativ", { relativ: "ueberfaellig" }), "datum", HEUTE)).toBe(false);
  });
  it("leer / nicht_leer; ohne Datum nie ein Treffer für Vergleiche", () => {
    expect(bedingungErfuellt(null, d("leer", undefined), "datum")).toBe(true);
    expect(bedingungErfuellt("2026-11-18", d("nicht_leer", undefined), "datum")).toBe(true);
    expect(bedingungErfuellt(null, d("vor", "2026-11-18"), "datum")).toBe(false);
  });
});

describe("zeitraumAufloesen (heute = Mi 18.11.2026)", () => {
  it("löst alle relativen Zeiträume auf", () => {
    expect(zeitraumAufloesen("woche", HEUTE)).toEqual({ von: "2026-11-16", bis: "2026-11-22" });
    expect(zeitraumAufloesen("monat", HEUTE)).toEqual({ von: "2026-11-01", bis: "2026-11-30" });
    expect(zeitraumAufloesen("naechste_7", HEUTE)).toEqual({ von: "2026-11-18", bis: "2026-11-24" });
    expect(zeitraumAufloesen("ueberfaellig", HEUTE)).toEqual({ bis: "2026-11-17" });
    expect(zeitraumAufloesen("heute", HEUTE)).toEqual({ von: "2026-11-18", bis: "2026-11-18" });
    expect(zeitraumAufloesen("letzte_30", HEUTE)).toEqual({ von: "2026-10-20", bis: "2026-11-18" });
  });
  it("Woche beginnt am Montag, auch wenn heute Sonntag ist", () => {
    expect(zeitraumAufloesen("woche", new Date(2026, 10, 22))).toEqual({ von: "2026-11-16", bis: "2026-11-22" });
  });
});

interface Zeile {
  titel: string;
  status: string;
  betrag: number;
}
const felder: FilterFeld<Zeile>[] = [
  { key: "titel", label: "Titel", typ: "text", icon: Building2, wert: (z) => z.titel },
  {
    key: "status",
    label: "Status",
    typ: "auswahl",
    icon: Building2,
    wert: (z) => z.status,
    optionen: [
      { wert: "neu", label: "Neu", status: "neu" },
      { wert: "arbeit", label: "In Arbeit", status: "arbeit" },
    ],
  },
  { key: "betrag", label: "Betrag", typ: "betrag", icon: Building2, wert: (z) => z.betrag },
  { key: "server", label: "Nur Server", typ: "text", icon: Building2 },
];
const zeilen: Zeile[] = [
  { titel: "Wartung Heizung", status: "neu", betrag: 500 },
  { titel: "Zählerschrank", status: "arbeit", betrag: 1500 },
  { titel: "Wartung PV", status: "arbeit", betrag: 2500 },
];

describe("filterAnwenden / sucheAnwenden", () => {
  it("verknüpft Bedingungen mit UND und überspringt Felder ohne wert()", () => {
    const r = filterAnwenden(
      zeilen,
      [
        { feld: "titel", op: "enthaelt", wert: "wartung" },
        { feld: "status", op: "ist", wert: ["arbeit"] },
        { feld: "server", op: "ist", wert: "egal" },
      ],
      felder,
    );
    expect(r.map((z) => z.titel)).toEqual(["Wartung PV"]);
    expect(filterAnwenden(zeilen, [], felder)).toBe(zeilen);
  });
  it("Suche: jedes Wort muss vorkommen, Reihenfolge egal, Umlaute normalisiert", () => {
    const text = (z: Zeile) => `${z.titel} ${z.status}`;
    expect(sucheAnwenden(zeilen, "pv wartung", text)).toHaveLength(1);
    expect(sucheAnwenden(zeilen, "zaehler", text)).toHaveLength(1);
    expect(sucheAnwenden(zeilen, "WARTUNG arbeit", text)).toHaveLength(1);
    expect(sucheAnwenden(zeilen, "wartung nix", text)).toHaveLength(0);
    expect(sucheAnwenden(zeilen, "   ", text)).toBe(zeilen);
  });
});

describe("pillenTeile", () => {
  it("zeigt Options-Labels, mehrere mit Komma", () => {
    expect(pillenTeile({ feld: "status", op: "ist", wert: ["neu", "arbeit"] }, felder[1])).toEqual({
      spalte: "Status",
      operator: "ist",
      wert: "Neu, In Arbeit",
    });
  });
  it("formatiert Betrag und Bereiche", () => {
    expect(pillenTeile({ feld: "betrag", op: "gte", wert: "1000" }, felder[2])).toEqual({ spalte: "Betrag", operator: "≥", wert: "1.000,00 €" });
    expect(pillenTeile({ feld: "betrag", op: "zwischen", wert: { von: "100", bis: "1.000,5" } }, felder[2]).wert).toBe("100,00 € – 1.000,50 €");
  });
  it("formatiert Datum, Datumsbereich und relativ", () => {
    const f: FilterFeld<Zeile> = { key: "faellig", label: "Fällig", typ: "datum", icon: Building2 };
    expect(pillenTeile({ feld: "faellig", op: "vor", wert: "2026-11-30" }, f).wert).toBe("30.11.2026");
    expect(pillenTeile({ feld: "faellig", op: "zwischen", wert: { von: "2026-10-01", bis: "2026-10-31" } }, f).wert).toBe("01.10. – 31.10.2026");
    expect(pillenTeile({ feld: "faellig", op: "relativ", wert: { relativ: "woche" } }, f)).toEqual({
      spalte: "Fällig",
      operator: "ist",
      wert: "diese Woche",
    });
  });
  it("leer-Operatoren haben keinen Wert", () => {
    expect(pillenTeile({ feld: "titel", op: "leer" }, felder[0])).toEqual({ spalte: "Titel", operator: "ist leer", wert: "" });
  });
});

describe("Hilfsfunktionen", () => {
  it("zuServerParametern führt die Abbildungen zusammen", () => {
    const r = zuServerParametern(
      [
        { feld: "status", op: "ist", wert: ["neu", "arbeit"] },
        { feld: "kunde", op: "ist", wert: ["k1"] },
        { feld: "unbekannt", op: "ist", wert: ["x"] },
      ],
      {
        status: (b) => ({ status: (b.wert as string[]).join(",") }),
        kunde: (b) => ({ kunde_id: (b.wert as string[])[0] }),
      },
    );
    expect(r).toEqual({ status: "neu,arbeit", kunde_id: "k1" });
  });
  it("auswahlKomplement", () => {
    expect(auswahlKomplement(["neu"], ["neu", "arbeit", "fertig"])).toEqual(["arbeit", "fertig"]);
    expect(auswahlKomplement(["neu"], [{ wert: "neu", label: "Neu" }, { wert: "x", label: "X" }])).toEqual(["x"]);
  });
  it("bedingungenGleich ignoriert Reihenfolge", () => {
    const a: FilterBedingung[] = [{ feld: "a", op: "ist", wert: ["1", "2"] }, { feld: "b", op: "leer" }];
    const b: FilterBedingung[] = [{ feld: "b", op: "leer" }, { feld: "a", op: "ist", wert: ["2", "1"] }];
    expect(bedingungenGleich(a, b)).toBe(true);
    expect(bedingungenGleich(a, [a[0]])).toBe(false);
  });
});
