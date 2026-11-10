import { describe, expect, it } from "vitest";

import { eRechnungModus, eRechnungPruefHinweis, leitwegIdFehler, leitwegPruefziffer } from "./eRechnungVersand";

describe("leitwegPruefziffer", () => {
  it("rechnet die Beispiel-IDs nach (wie das Backend)", () => {
    expect(leitwegPruefziffer("99112345")).toBe("73");
    expect(leitwegPruefziffer("040110001234512345")).toBe("06");
  });

  it("wandelt Buchstaben der Feinadressierung wie die IBAN (A=10)", () => {
    // gleicher Wert wie backend/tests/test_xrechnung.py::test_leitweg_mit_buchstaben_in_der_feinadressierung
    expect(leitwegPruefziffer("99ABC123")).toBe(leitwegPruefziffer("99" + "101112" + "123"));
  });
});

describe("leitwegIdFehler", () => {
  it("akzeptiert gültige IDs, auch mit Leerraum und Kleinschreibung", () => {
    expect(leitwegIdFehler("04011000-1234512345-06")).toBeNull();
    expect(leitwegIdFehler(" 991-12345-73 ")).toBeNull();
    expect(leitwegIdFehler("04011000 - 1234512345 - 06")).toBeNull();
  });

  it("lässt eine leere Eingabe zu", () => {
    expect(leitwegIdFehler("")).toBeNull();
    expect(leitwegIdFehler("   ")).toBeNull();
  });

  it("meldet falsches Format und falsche Prüfziffer verständlich", () => {
    expect(leitwegIdFehler("991-12345")).toMatch(/Format/);
    expect(leitwegIdFehler("9-12345-73")).toMatch(/Format/);
    expect(leitwegIdFehler("991-12_45-73")).toMatch(/Format/);
    expect(leitwegIdFehler("991-12345-74")).toMatch(/Prüfziffer/);
  });
});

describe("eRechnungModus", () => {
  it("nutzt den gespeicherten Modus, sonst e_rechnung_aktiv", () => {
    expect(eRechnungModus({ e_rechnung_modus: "b2b", e_rechnung_aktiv: true })).toBe("b2b");
    expect(eRechnungModus({ e_rechnung_aktiv: true })).toBe("alle");
    expect(eRechnungModus({ e_rechnung_aktiv: false })).toBe("aus");
    expect(eRechnungModus({})).toBe("aus");
  });
});

describe("eRechnungPruefHinweis", () => {
  it("benennt das Profil und die Leitweg-ID", () => {
    expect(eRechnungPruefHinweis("xrechnung", "991-12345-73")).toBe(
      "E-Rechnung (XRechnung) – interne Pflichtfeldprüfung bestanden. Leitweg-ID: 991-12345-73.",
    );
    expect(eRechnungPruefHinweis("en16931")).toBe("E-Rechnung (ZUGFeRD) – interne Pflichtfeldprüfung bestanden.");
  });

  it("liefert null ohne E-Rechnung", () => {
    expect(eRechnungPruefHinweis(null)).toBeNull();
    expect(eRechnungPruefHinweis(undefined)).toBeNull();
  });
});
