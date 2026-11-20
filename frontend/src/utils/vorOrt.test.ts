import { describe, expect, it } from "vitest";

import type { VorOrtKontakt, VorOrtKontaktZugeordnet } from "../types";
import {
  auswahlGruppen,
  geerbtFussnote,
  kontaktAnzeigename,
  nachStandortGruppieren,
  pruefeKontaktForm,
  leereKontaktForm,
  kontaktFormZuBody,
  standortBegriff,
  telHref,
} from "./vorOrt";

const k = (id: string, extra: Partial<VorOrtKontakt> = {}) =>
  ({ id, standort_id: null, standort_bezeichnung: null, name: id, rolle: "mieter", telefon: null, anonymisiert_am: null, ...extra }) as VorOrtKontakt;

describe("vorOrt utils", () => {
  it("telHref entfernt Trennzeichen, behält +", () => {
    expect(telHref("+49 (171) 123-45")).toBe("tel:+4917112345");
  });

  it("Anzeigename: anonymisiert, Name, Telefon, Rolle", () => {
    expect(kontaktAnzeigename(k("a", { anonymisiert_am: "2026-01-01" }))).toBe("Kontakt anonymisiert");
    expect(kontaktAnzeigename(k("a", { name: null, telefon: "0171" }))).toBe("0171");
    expect(kontaktAnzeigename(k("a", { name: null }))).toBe("Mieter/in");
  });

  it("Pflicht: Name oder Telefon", () => {
    const f = leereKontaktForm();
    expect(pruefeKontaktForm(f)).toBe("Name oder Telefon angeben");
    expect(pruefeKontaktForm({ ...f, telefon: "0171" })).toBeNull();
    expect(kontaktFormZuBody({ ...f, name: " Anna " }).name).toBe("Anna");
    expect(kontaktFormZuBody(f).telefon).toBeNull();
    expect("standort_id" in kontaktFormZuBody(f)).toBe(false);
    expect(kontaktFormZuBody({ ...f, standortId: "s1" }, true).standort_id).toBe("s1");
  });

  it("Auswahlgruppen: Ziel-Standort zuerst, Zugeordnete und Anonymisierte raus", () => {
    const gruppen = auswahlGruppen(
      [
        k("a", { standort_id: "s1", standort_bezeichnung: "Mosel" }),
        k("b", { standort_id: "s2" }),
        k("c", { standort_id: "s1", standort_bezeichnung: "Mosel" }),
        k("d", { anonymisiert_am: "2026-01-01" }),
      ],
      "s1",
      new Set(["c"]),
    );
    expect(gruppen.map((g) => [g.titel, g.kontakte.map((x) => x.id)])).toEqual([
      ["Bekannt in Mosel", ["a"]],
      ["Weitere Kontakte des Kunden", ["b"]],
    ]);
  });

  it("Gruppierung nach Standort mit 'Ohne' zuletzt", () => {
    const g = nachStandortGruppieren([k("a"), k("b", { standort_id: "s1", standort_bezeichnung: "Zeta" }), k("c", { standort_id: "s2", standort_bezeichnung: "Alpha" })]);
    expect(g.map((x) => x.titel)).toEqual(["Alpha", "Zeta", null]);
  });

  it("Fußnote nur wenn alle geerbt sind", () => {
    const z = (herkunft: "vorgang" | "auftrag") =>
      ({ herkunft, herkunft_titel: "Heizung" }) as VorOrtKontaktZugeordnet;
    expect(geerbtFussnote([z("auftrag")], "vorgang")).toBe("Vom Auftrag ‚Heizung‘ übernommen.");
    expect(geerbtFussnote([z("auftrag"), z("vorgang")], "vorgang")).toBeNull();
    expect(geerbtFussnote([], "vorgang")).toBeNull();
  });

  it("Hausverwaltung: Liegenschaft", () => {
    expect(standortBegriff("hausverwaltung")).toBe("Liegenschaft");
    expect(standortBegriff("privat")).toBe("Standort");
  });
});
