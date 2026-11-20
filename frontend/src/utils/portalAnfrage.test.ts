import { describe, expect, it } from "vitest";

import { baueKontakteBody, leererPortalKontakt, validierePortalKontakte } from "./portalAnfrage";

describe("Portal-Anfrage: Kontakte vor Ort", () => {
  it("ignoriert komplett leere Zeilen", () => {
    expect(validierePortalKontakte([leererPortalKontakt()])).toEqual({});
    expect(baueKontakteBody([leererPortalKontakt()])).toEqual([]);
  });

  it("verlangt je Kontakt Name oder Telefon", () => {
    const nurHinweis = { ...leererPortalKontakt(), hinweis: "Klingel defekt" };
    expect(validierePortalKontakte([leererPortalKontakt(), nurHinweis])).toEqual({ 1: "Bitte Name oder Telefon angeben." });
    expect(validierePortalKontakte([{ ...nurHinweis, telefon: "0176 22 45 18" }])).toEqual({});
  });

  it("baut den Body mit getrimmten Werten und null für Leeres", () => {
    const body = baueKontakteBody([{ name: " Anna Becker ", rolle: "mieter", telefon: "", erreichbarkeit: "nachmittags", hinweis: "" }]);
    expect(body).toEqual([{ name: "Anna Becker", rolle: "mieter", telefon: null, erreichbarkeit: "nachmittags", hinweis: null }]);
  });

  it("sendet höchstens fünf Kontakte", () => {
    const sechs = Array.from({ length: 6 }, (_, i) => ({ ...leererPortalKontakt(), name: `K${i}` }));
    expect(baueKontakteBody(sechs)).toHaveLength(5);
  });
});
