import { describe, expect, it } from "vitest";

import type { PositionDetail, RechteRegistry } from "../../types/organigramm";
import {
  aktionsSpalten,
  herkunftTexte,
  overridesAusZustaenden,
  scopeOptionen,
  vorlagenScopes,
  wertZuZustand,
  wirksamerScope,
  zellenArt,
  zustaendeAusOverrides,
  zustaendeGleich,
  zustandZuWert,
  type ZellenZustand,
} from "./rechteMatrix";

const REGISTRY: RechteRegistry = {
  scopes: ["eigene", "team", "teilbaum", "bereich", "mandant"],
  bereiche: [
    { key: "vorgaenge", label: "Aufträge", aktionen: ["sehen", "erstellen", "bearbeiten", "loeschen", "exportieren"], scopes: ["eigene", "team", "teilbaum", "bereich", "mandant"], modul: null },
    { key: "material", label: "Material", aktionen: ["sehen", "erstellen", "bearbeiten", "loeschen", "exportieren"], scopes: ["mandant"], modul: "material" },
    { key: "abrechnung", label: "Angebote & Rechnungen", aktionen: ["sehen", "freigeben"], scopes: ["mandant"], modul: null },
  ],
};

describe("Registry-getriebene Matrix", () => {
  it("bildet die Spalten aus der Vereinigung aller Aktionen in Registry-Reihenfolge", () => {
    expect(aktionsSpalten(REGISTRY)).toEqual(["sehen", "erstellen", "bearbeiten", "loeschen", "exportieren", "freigeben"]);
  });

  it("bietet je Bereich nur Scopes aus der Registry an", () => {
    expect(scopeOptionen(REGISTRY, "vorgaenge")).toEqual(["eigene", "team", "teilbaum", "bereich", "mandant"]);
    expect(scopeOptionen(REGISTRY, "material")).toEqual(["mandant"]);
    expect(scopeOptionen(REGISTRY, "unbekannt")).toEqual([]);
  });
});

describe("Zellzustaende", () => {
  const vorlage: ZellenZustand = { modus: "vorlage" };

  it("unterscheidet Vorlage erlaubt/nicht, zusaetzlich erlaubt und verweigert", () => {
    expect(zellenArt(vorlage, "team")).toBe("vorlage_erlaubt");
    expect(zellenArt(vorlage, null)).toBe("vorlage_nein");
    expect(zellenArt({ modus: "erlaubt", scope: "mandant" }, null)).toBe("zusaetzlich");
    expect(zellenArt({ modus: "verweigert" }, "mandant")).toBe("verweigert");
  });

  it("verengt den Vorlagen-Scope durch einen Override nicht (wie die Engine)", () => {
    expect(wirksamerScope({ modus: "erlaubt", scope: "eigene" }, "mandant")).toBe("mandant");
    expect(wirksamerScope({ modus: "erlaubt", scope: "mandant" }, "eigene")).toBe("mandant");
    expect(wirksamerScope({ modus: "verweigert" }, "mandant")).toBeNull();
    expect(wirksamerScope(vorlage, "team")).toBe("team");
  });

  it("uebersetzt zwischen Select-Wert und Zustand", () => {
    for (const z of [vorlage, { modus: "verweigert" }, { modus: "erlaubt", scope: "teilbaum" }] as ZellenZustand[]) {
      expect(wertZuZustand(zustandZuWert(z))).toEqual(z);
    }
  });

  it("liest Zustaende aus gespeicherten Overrides", () => {
    const karte = zustaendeAusOverrides([
      { bereich: "vorgaenge", aktion: "loeschen", wirkung: "verweigern", scope: null },
      { bereich: "material", aktion: "sehen", wirkung: "erlauben", scope: "mandant" },
      { bereich: "abrechnung", aktion: "freigeben", wirkung: "erlauben", scope: null },
    ]);
    expect(karte.get("vorgaenge.loeschen")).toEqual({ modus: "verweigert" });
    expect(karte.get("material.sehen")).toEqual({ modus: "erlaubt", scope: "mandant" });
    expect(karte.get("abrechnung.freigeben")).toEqual({ modus: "erlaubt", scope: "mandant" });
  });
});

describe("overridesAusZustaenden (PUT-Payload)", () => {
  it("laesst Vorlage-Zellen weg und setzt beim Verweigern keinen Scope", () => {
    const z = new Map<string, ZellenZustand>([
      ["vorgaenge.sehen", { modus: "erlaubt", scope: "team" }],
      ["vorgaenge.loeschen", { modus: "verweigert" }],
      ["material.sehen", { modus: "vorlage" }],
    ]);
    expect(overridesAusZustaenden(z, REGISTRY)).toEqual([
      { bereich: "vorgaenge", aktion: "sehen", wirkung: "erlauben", scope: "team" },
      { bereich: "vorgaenge", aktion: "loeschen", wirkung: "verweigern" },
    ]);
  });

  it("verwirft Scopes und Aktionen, die die Registry fuer den Bereich nicht kennt", () => {
    const z = new Map<string, ZellenZustand>([
      ["material.sehen", { modus: "erlaubt", scope: "team" }],
      ["abrechnung.loeschen", { modus: "verweigert" }],
      ["gibtsnicht.sehen", { modus: "verweigert" }],
    ]);
    expect(overridesAusZustaenden(z, REGISTRY)).toEqual([]);
  });

  it("erkennt unveraenderte Zustaende unabhaengig von Vorlage-Eintraegen", () => {
    const a = new Map<string, ZellenZustand>([["vorgaenge.sehen", { modus: "verweigert" }]]);
    const b = new Map<string, ZellenZustand>([
      ["vorgaenge.sehen", { modus: "verweigert" }],
      ["material.sehen", { modus: "vorlage" }],
    ]);
    expect(zustaendeGleich(a, b)).toBe(true);
    expect(zustaendeGleich(a, new Map())).toBe(false);
  });
});

describe("vorlagenScopes", () => {
  const detail: Pick<PositionDetail, "effektive_rechte" | "overrides" | "diff_zur_vorlage"> = {
    effektive_rechte: [
      { bereich: "vorgaenge", aktion: "sehen", scope: "team", herkunft: [{ art: "account_typ" }] },
      { bereich: "material", aktion: "sehen", scope: "mandant", herkunft: [{ art: "position_override", wirkung: "erlauben" }] },
    ],
    overrides: [
      { bereich: "material", aktion: "sehen", wirkung: "erlauben", scope: "mandant" },
      { bereich: "vorgaenge", aktion: "loeschen", wirkung: "verweigern", scope: null },
    ],
    diff_zur_vorlage: [
      { bereich: "material", aktion: "sehen", art: "hinzugefuegt", typ_scope: null, position_scope: "mandant" },
      { bereich: "vorgaenge", aktion: "loeschen", art: "entfernt", typ_scope: "mandant", position_scope: null },
    ],
  };

  it("leitet den Vorlagen-Scope aus Effektiv, Overrides und Diff ab", () => {
    const k = vorlagenScopes(detail);
    expect(k.get("vorgaenge.sehen")).toBe("team");
    expect(k.get("material.sehen")).toBeNull();
    expect(k.get("vorgaenge.loeschen")).toBe("mandant");
  });
});

describe("herkunftTexte", () => {
  it("loest Account-Typ- und Positionsnamen auf", () => {
    const t = herkunftTexte(
      [
        { art: "account_typ", account_typ_id: "t1", position_id: "p1" },
        { art: "position_override", wirkung: "erlauben", position_id: "p1" },
        { art: "user_override", wirkung: "verweigern" },
      ],
      { accountTyp: () => "Techniker", position: () => "Teamleitung" },
    );
    expect(t[0]).toContain("Techniker");
    expect(t[1]).toContain("Teamleitung");
    expect(t[2]).toBe("Verweigert (Override am Nutzer)");
  });
});
