import { describe, expect, it } from "vitest";

import type { CurrentUser, RechteAktion, RechteBereich, Role } from "../types";
import { routeErlaubt, type RoutenKontext } from "./routenRechte";
import { sichtbareNavSeiten } from "./navSeiten";

function kontext(
  role: Role,
  rechte: Partial<Record<RechteBereich, RechteAktion[]>> = {},
  extra: Partial<CurrentUser> = {},
  oberflaeche: "office" | "feld" = "office",
): RoutenKontext {
  const alleRechte = role !== "custom";
  const currentUser = { role, rechte, deaktivierte_module: [], ...extra } as CurrentUser;
  return {
    currentUser,
    hatRecht: (b, a) => alleRechte || (rechte[b]?.includes(a) ?? false),
    oberflaeche,
  };
}

const ADMIN_PFADE = ["/accounts", "/account-typen", "/anlagen-felder", "/integrationen"];

describe("routeErlaubt", () => {
  it("Techniker ohne Rechte sieht keinen der Admin-Bereiche", () => {
    const techniker = kontext("custom", { vorgaenge: ["sehen"] });
    for (const pfad of ["/accounts", "/integrationen", "/anlagen-felder", "/techniker-zuweisungen"]) {
      expect(routeErlaubt(pfad, techniker), pfad).toBe(false);
    }
    // Account-Typen nur mit rechte_verwalten (Backend _verwalter).
    expect(routeErlaubt("/account-typen", techniker)).toBe(false);
    expect(routeErlaubt("/einstellungen", techniker)).toBe(false);
    expect(routeErlaubt("/form-schemas", techniker)).toBe(false);
    expect(routeErlaubt("/plan-symbole", techniker)).toBe(false);
    const namen = sichtbareNavSeiten(techniker.currentUser, techniker.hatRecht).map((s) => s.key);
    expect(namen).not.toContain("nutzer");
    expect(namen).not.toContain("integrationen");
    expect(namen).not.toContain("anlagen_felder");
  });

  it("mandant_admin darf alle Admin-Bereiche", () => {
    const admin = kontext("mandant_admin");
    for (const pfad of [...ADMIN_PFADE, "/einstellungen", "/einstellungen/export", "/protokoll", "/plan-symbole"]) {
      expect(routeErlaubt(pfad, admin), pfad).toBe(true);
    }
  });

  it("custom: Einstellungen und Account-Typen ja, Export/Kategorien nein", () => {
    const custom = kontext("custom", { kunden: ["sehen"] });
    expect(routeErlaubt("/einstellungen", custom)).toBe(true);
    expect(routeErlaubt("/einstellungen/seitenleiste", custom)).toBe(true);
    expect(routeErlaubt("/account-typen", custom)).toBe(false);
    expect(routeErlaubt("/account-typen", kontext("custom", { organigramm: ["rechte_verwalten"] }))).toBe(true);
    expect(routeErlaubt("/anlagen-felder", custom)).toBe(true);
    expect(routeErlaubt("/einstellungen/export", custom)).toBe(false);
    expect(routeErlaubt("/integrationen", custom)).toBe(false);
  });

  it("loesch_operativ erbt Admin, loesch_ansicht nicht", () => {
    expect(routeErlaubt("/accounts", kontext("loesch_operativ"))).toBe(true);
    expect(routeErlaubt("/einstellungen/export", kontext("loesch_operativ"))).toBe(false);
    expect(routeErlaubt("/accounts", kontext("loesch_ansicht"))).toBe(false);
    expect(routeErlaubt("/papierkorb", kontext("loesch_ansicht"))).toBe(true);
    expect(routeErlaubt("/papierkorb", kontext("mandant_admin"))).toBe(false);
  });

  it("Detailseiten folgen dem Recht der Liste", () => {
    const ohne = kontext("custom", {});
    expect(routeErlaubt("/kunden/1", ohne)).toBe(false);
    expect(routeErlaubt("/anlagen/1", ohne)).toBe(false);
    expect(routeErlaubt("/rechnungen/1", ohne)).toBe(false);
    expect(routeErlaubt("/angebote/1", ohne)).toBe(false);
    expect(routeErlaubt("/material/1", ohne)).toBe(false);
    expect(routeErlaubt("/kunden/1", kontext("custom", { kunden: ["sehen"] }))).toBe(true);
    expect(routeErlaubt("/anlagen/1", kontext("custom", { kunden: ["sehen"] }))).toBe(true);
  });

  it("/projekte: Zeitplan-Recht reicht nur in der Feld-App", () => {
    const rechte = { projekte: ["zeitplan_sehen"] as RechteAktion[] };
    expect(routeErlaubt("/projekte", kontext("custom", rechte, {}, "feld"))).toBe(true);
    expect(routeErlaubt("/projekte/abc/zeitplan", kontext("custom", rechte, {}, "feld"))).toBe(true);
    expect(routeErlaubt("/projekte", kontext("custom", rechte, {}, "office"))).toBe(false);
    expect(routeErlaubt("/projekte", kontext("custom", {}, {}, "feld"))).toBe(false);
  });

  it("deaktiviertes Modul sperrt", () => {
    const ctx = kontext("mandant_admin", {}, { deaktivierte_module: ["material"] });
    expect(routeErlaubt("/material", ctx)).toBe(false);
    expect(routeErlaubt("/material/1", ctx)).toBe(false);
  });

  it("Pfade ohne Regel bleiben offen", () => {
    const ohne = kontext("custom", {});
    for (const pfad of ["/mehr", "/neu", "/suche", "/vorgaenge/1", "/unbekannt"]) {
      expect(routeErlaubt(pfad, ohne), pfad).toBe(true);
    }
  });

  it("Dauerauftraege: Modul, dispo.sehen, /neu braucht dispo.erstellen", () => {
    const sehen = kontext("custom", { dispo: ["sehen"] });
    expect(routeErlaubt("/dauerauftraege", sehen)).toBe(true);
    expect(routeErlaubt("/dauerauftraege/1", sehen)).toBe(true);
    expect(routeErlaubt("/dauerauftraege/neu", sehen)).toBe(false);
    expect(routeErlaubt("/dauerauftraege/neu", kontext("custom", { dispo: ["sehen", "erstellen"] }))).toBe(true);
    expect(routeErlaubt("/dauerauftraege", kontext("custom", {}))).toBe(false);
    const ohneModul = kontext("mandant_admin", {}, { deaktivierte_module: ["dauerauftrag"] });
    expect(routeErlaubt("/dauerauftraege", ohneModul)).toBe(false);
  });

  it("/standorte/:id braucht kunden.sehen", () => {
    expect(routeErlaubt("/standorte/1", kontext("custom", {}))).toBe(false);
    expect(routeErlaubt("/standorte/1", kontext("custom", { kunden: ["sehen"] }))).toBe(true);
  });

  it("loesch_ansicht darf nur Papierkorb, Profil und Mehr", () => {
    const la = kontext("loesch_ansicht");
    for (const pfad of ["/papierkorb", "/profil", "/mehr"]) expect(routeErlaubt(pfad, la), pfad).toBe(true);
    for (const pfad of ["/feed", "/vorgaenge/1", "/neu", "/suche", "/kunden", "/dauerauftraege"]) {
      expect(routeErlaubt(pfad, la), pfad).toBe(false);
    }
  });

  it("Techniker (custom ohne Rechte) sieht die Admin-Seiten nicht", () => {
    const t = kontext("custom", { vorgaenge: ["sehen"] });
    for (const pfad of ["/accounts", "/form-schemas", "/plan-symbole", "/techniker-zuweisungen", "/integrationen"]) {
      expect(routeErlaubt(pfad, t), pfad).toBe(false);
    }
  });

  it("Seed-Techniker: Admin-Seiten gesperrt, Einstellungen nur wegen Anlagen-Zusatzfeldern offen", () => {
    const t = kontext("custom", {
      vorgaenge: ["sehen", "erstellen", "bearbeiten"],
      kunden: ["sehen"],
      material: ["sehen"],
      dispo: ["sehen"],
      projekte: ["zeitplan_sehen"],
    });
    for (const pfad of ["/accounts", "/account-typen", "/form-schemas", "/plan-symbole", "/techniker-zuweisungen", "/integrationen"]) {
      expect(routeErlaubt(pfad, t), pfad).toBe(false);
    }
    expect(routeErlaubt("/einstellungen", t)).toBe(true);
  });
});
