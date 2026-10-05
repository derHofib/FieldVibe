import { describe, expect, it } from "vitest";

import type { RechteRegistry } from "../types/organigramm";
import { ACCOUNT_TYP_VORLAGEN, vorlagenRechte } from "./accountTypVorlagen";

const BASIS = ["sehen", "erstellen", "bearbeiten", "loeschen", "exportieren"];
const REGISTRY: RechteRegistry = {
  scopes: ["eigene", "mandant"],
  bereiche: [
    { key: "vorgaenge", label: "Aufträge", aktionen: BASIS, scopes: ["eigene", "mandant"], modul: null },
    { key: "projekte", label: "Projekte", aktionen: [...BASIS, "freigeben", "zeitplan_sehen", "zeitplan_beantragen"], scopes: ["mandant"], modul: null },
    { key: "organigramm", label: "Organigramm", aktionen: [...BASIS, "rechte_verwalten"], scopes: ["mandant"], modul: null },
    { key: "mitarbeiterverwaltung", label: "Mitarbeiterliste", aktionen: [...BASIS, "rechte_verwalten"], scopes: ["mandant"], modul: null },
  ],
};

const vorlage = (key: string) => ACCOUNT_TYP_VORLAGEN.find((v) => v.key === key)!;
const aktionen = (key: string, bereich: string) =>
  vorlagenRechte(vorlage(key), REGISTRY)
    .filter((r) => r.bereich === bereich)
    .map((r) => r.aktion);

describe("Systemvorlagen", () => {
  it("bietet die sechs verlangten Vorlagen mit eindeutigem Schluessel und Namen", () => {
    expect(ACCOUNT_TYP_VORLAGEN.map((v) => v.name)).toEqual([
      "Geschäftsführer",
      "Bereichsleiter",
      "Teamleiter",
      "Mitarbeiter",
      "Stabsstelle",
      "Admin",
    ]);
    expect(new Set(ACCOUNT_TYP_VORLAGEN.map((v) => v.key)).size).toBe(6);
  });

  it("gibt Geschaeftsfuehrer und Admin alle Aktionen aller Bereiche der Registry", () => {
    const gesamt = REGISTRY.bereiche.reduce((n, b) => n + b.aktionen.length, 0);
    expect(vorlagenRechte(vorlage("geschaeftsfuehrer"), REGISTRY)).toHaveLength(gesamt);
    expect(vorlagenRechte(vorlage("admin"), REGISTRY)).toHaveLength(gesamt);
    expect(aktionen("admin", "organigramm")).toContain("rechte_verwalten");
  });

  it("nimmt dem Bereichsleiter rechte_verwalten in Fachbereichen, gibt es ihm aber im Organigramm", () => {
    expect(aktionen("bereichsleiter", "vorgaenge")).toEqual(BASIS);
    expect(aktionen("bereichsleiter", "organigramm")).toEqual(["sehen", "erstellen", "bearbeiten", "rechte_verwalten"]);
  });

  it("laesst den Mitarbeiter keine Verwaltungsrechte erhalten und markiert nur zugewiesene Kunden", () => {
    const mitarbeiter = vorlagenRechte(vorlage("mitarbeiter"), REGISTRY);
    expect(mitarbeiter.some((r) => r.aktion === "rechte_verwalten" || r.aktion === "loeschen")).toBe(false);
    expect(aktionen("mitarbeiter", "projekte")).toEqual(["zeitplan_sehen", "zeitplan_beantragen"]);
    expect(aktionen("mitarbeiter", "organigramm")).toEqual([]);
    expect(vorlage("mitarbeiter").flags.nur_zugewiesene_kunden).toBe(true);
  });

  it("gibt der Stabsstelle nur lesende Rechte plus Export", () => {
    const stab = vorlagenRechte(vorlage("stabsstelle"), REGISTRY);
    expect(stab.every((r) => ["sehen", "exportieren"].includes(r.aktion))).toBe(true);
    expect(stab.length).toBeGreaterThan(0);
  });

  it("verwirft Aktionen und Bereiche, die die Registry nicht kennt", () => {
    const schmal: RechteRegistry = {
      scopes: ["mandant"],
      bereiche: [{ key: "vorgaenge", label: "Aufträge", aktionen: ["sehen"], scopes: ["mandant"], modul: null }],
    };
    expect(vorlagenRechte(vorlage("geschaeftsfuehrer"), schmal)).toEqual([{ bereich: "vorgaenge", aktion: "sehen" }]);
  });
});
