import { describe, expect, it } from "vitest";

import { eRechnungSyntaxLabel, hinweisZeilen, pruefeERechnungDatei } from "./eRechnung";

describe("eRechnungSyntaxLabel", () => {
  it("benennt CII und UBL", () => {
    expect(eRechnungSyntaxLabel("cii")).toBe("XRechnung / ZUGFeRD (CII)");
    expect(eRechnungSyntaxLabel("ubl")).toBe("XRechnung (UBL)");
  });

  it("liefert null ohne Syntax und einen Standardnamen für Unbekanntes", () => {
    expect(eRechnungSyntaxLabel(null)).toBeNull();
    expect(eRechnungSyntaxLabel(undefined)).toBeNull();
    expect(eRechnungSyntaxLabel("edifact")).toBe("E-Rechnung");
  });
});

describe("hinweisZeilen", () => {
  it("zerlegt den Importhinweis zeilenweise", () => {
    expect(hinweisZeilen("Mehrere Steuersätze (19 %, 7 %) – Vorsteuer bitte prüfen\n\n Gutschrift \n")).toEqual([
      "Mehrere Steuersätze (19 %, 7 %) – Vorsteuer bitte prüfen",
      "Gutschrift",
    ]);
  });

  it("ist ohne Hinweis leer", () => {
    expect(hinweisZeilen(null)).toEqual([]);
    expect(hinweisZeilen("")).toEqual([]);
  });
});

describe("pruefeERechnungDatei", () => {
  it("akzeptiert XML und PDF unabhängig von der Groß-/Kleinschreibung", () => {
    expect(pruefeERechnungDatei({ name: "RE-1.XML", size: 1000 })).toBeNull();
    expect(pruefeERechnungDatei({ name: "rechnung.pdf", size: 1000 })).toBeNull();
  });

  it("lehnt andere Dateitypen ab", () => {
    expect(pruefeERechnungDatei({ name: "foto.jpg", size: 10 })).toMatch(/XML-Datei/);
  });

  it("begrenzt XML auf 5 MB und PDF auf 10 MB", () => {
    expect(pruefeERechnungDatei({ name: "a.xml", size: 5 * 1024 * 1024 + 1 })).toMatch(/max\. 5 MB/);
    expect(pruefeERechnungDatei({ name: "a.pdf", size: 6 * 1024 * 1024 })).toBeNull();
    expect(pruefeERechnungDatei({ name: "a.pdf", size: 10 * 1024 * 1024 + 1 })).toMatch(/max\. 10 MB/);
  });
});
