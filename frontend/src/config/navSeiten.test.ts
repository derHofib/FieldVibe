import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import type { CurrentUser, MandantModul, RechteAktion, RechteBereich, Role } from "../types";
import { NAV_SEITEN, sichtbareNavSeiten } from "./navSeiten";

type Rechte = Partial<Record<RechteBereich, RechteAktion[]>>;
type Nutzer = Pick<CurrentUser, "role" | "deaktivierte_module" | "nur_zugewiesene_kunden"> &
  Pick<CurrentUser, "darf_zeiten_buchen" | "darf_abwesenheiten_verwalten"> & { rechte: Rechte };

// Soll-Zustand aus den Backend-Routern (app/api/routes/*.py): wer eine Seite sieht, darf ihren
// Haupt-Endpunkt aufrufen (kein 403/404). loesch_operativ besteht jedes require_roles mit
// "mandant_admin" (app/api/deps.py); nur_mandant_admin schliesst es aus.
interface BackendGate {
  rollen: Role[];
  recht?: [RechteBereich, RechteAktion][];
  rechteOder?: [RechteBereich, RechteAktion][];
  modul?: MandantModul;
  extra?: (n: Nutzer) => boolean;
}

const ALLE_STAFF: Role[] = ["mandant_admin", "custom", "loesch_operativ"];
const ADMIN: Role[] = ["mandant_admin", "loesch_operativ"];

const BACKEND: Record<string, BackendGate> = {
  feed: { rollen: ALLE_STAFF },
  profil: { rollen: ["mandant_admin", "custom", "loesch_operativ", "loesch_ansicht"] },
  boards: { rollen: ["mandant_admin", "custom", "loesch_operativ"] },
  dispo: { rollen: ALLE_STAFF, recht: [["dispo", "sehen"]], modul: "dispo" },
  projekte: { rollen: ALLE_STAFF, recht: [["projekte", "sehen"]] },
  zeitplaene: { rollen: ALLE_STAFF },
  auftraege: { rollen: ALLE_STAFF, recht: [["projekte", "sehen"]] },
  "meine-aufgaben": { rollen: ALLE_STAFF },
  kunden: { rollen: ALLE_STAFF, recht: [["kunden", "sehen"]] },
  partner: { rollen: ALLE_STAFF, modul: "nachunternehmer" },
  material: { rollen: ALLE_STAFF, recht: [["material", "sehen"]], modul: "material" },
  zeiterfassung: { rollen: ALLE_STAFF, modul: "zeiterfassung" },
  zeiten_buchen: { rollen: ALLE_STAFF, modul: "zeiterfassung", extra: (n) => n.darf_zeiten_buchen },
  pruefmittel: { rollen: ALLE_STAFF, modul: "pruefzyklen" },
  anfragen: { rollen: ["mandant_admin", "custom", "loesch_operativ"], recht: [["vorgaenge", "bearbeiten"]] },
  rechnungen: { rollen: ALLE_STAFF, recht: [["abrechnung", "sehen"]], modul: "abrechnung" },
  leistungsverzeichnis: { rollen: ALLE_STAFF, recht: [["kunden", "sehen"]] },
  rechnungseingang: { rollen: ALLE_STAFF, recht: [["abrechnung", "sehen"]], modul: "abrechnung" },
  buchhaltung: {
    rollen: ["mandant_admin", "custom", "loesch_operativ"],
    recht: [["abrechnung", "sehen"]],
    modul: "abrechnung",
    extra: (n) => !n.nur_zugewiesene_kunden,
  },
  kennzahlen: { rollen: ADMIN, modul: "statistik" },
  meldungen: { rollen: ALLE_STAFF },
  postfach: { rollen: ["mandant_admin", "custom", "loesch_operativ"], modul: "postfach" },
  highlights: { rollen: ["mandant_admin", "custom", "loesch_operativ"], recht: [["vorgaenge", "sehen"]], modul: "highlights" },
  nutzer: { rollen: ["mandant_admin", "custom", "loesch_operativ"], recht: [["mitarbeiterverwaltung", "sehen"]] },
  account_typen: {
    rollen: ["mandant_admin", "custom", "loesch_operativ"],
    rechteOder: [
      ["organigramm", "rechte_verwalten"],
      ["mitarbeiterverwaltung", "rechte_verwalten"],
    ],
  },
  organigramm: { rollen: ALLE_STAFF, recht: [["organigramm", "sehen"]] },
  techniker_zuweisungen: { rollen: ["mandant_admin", "custom", "loesch_operativ"], recht: [["kunden", "bearbeiten"]] },
  abwesenheiten: { rollen: ["mandant_admin", "custom", "loesch_operativ"], modul: "zeiterfassung", extra: (n) => n.darf_abwesenheiten_verwalten },
  team_zeiten: { rollen: ["mandant_admin", "custom", "loesch_operativ"], recht: [["mitarbeiterverwaltung", "bearbeiten"]], modul: "zeiterfassung" },
  anlagen_felder: { rollen: ALLE_STAFF, recht: [["kunden", "sehen"]] },
  formulare: { rollen: ["mandant_admin", "custom", "loesch_operativ"], recht: [["formulare", "sehen"]] },
  integrationen: { rollen: ADMIN },
  protokoll: { rollen: ["mandant_admin"] },
  datenimport: { rollen: ADMIN },
  export: { rollen: ["mandant_admin"] },
  papierkorb: { rollen: ["loesch_ansicht", "loesch_operativ"] },
};

const ALLE_BEREICHE: RechteBereich[] = [
  "dispo", "projekte", "kunden", "material", "abrechnung", "vorgaenge", "mitarbeiterverwaltung",
  "organigramm", "formulare", "partner", "statistik", "fehlerberichte",
] as RechteBereich[];
const ALLE_AKTIONEN: RechteAktion[] = [
  "sehen", "erstellen", "bearbeiten", "loeschen", "exportieren", "freigeben", "rechte_verwalten", "zeitplan_sehen",
] as RechteAktion[];

const ALLES: Rechte = Object.fromEntries(ALLE_BEREICHE.map((b) => [b, ALLE_AKTIONEN])) as Rechte;

function nutzer(role: Role, rechte: Rechte, extra: Partial<Nutzer> = {}): Nutzer {
  return {
    role,
    rechte,
    deaktivierte_module: [],
    nur_zugewiesene_kunden: false,
    darf_zeiten_buchen: false,
    darf_abwesenheiten_verwalten: false,
    ...extra,
  };
}

// Rechte-Matrix wie /api/auth/me: alle Nicht-custom-Rollen bekommen alles.
const NUTZER: Record<string, Nutzer> = {
  mandant_admin: nutzer("mandant_admin", ALLES, { darf_zeiten_buchen: true, darf_abwesenheiten_verwalten: true }),
  loesch_operativ: nutzer("loesch_operativ", ALLES, { darf_zeiten_buchen: true, darf_abwesenheiten_verwalten: true }),
  loesch_ansicht: nutzer("loesch_ansicht", ALLES),
  custom_ohne_rechte: nutzer("custom", {}),
  custom_techniker: nutzer("custom", { vorgaenge: ["sehen"], projekte: ["zeitplan_sehen"] }),
  custom_dispo: nutzer("custom", { dispo: ["sehen", "bearbeiten"], vorgaenge: ["sehen", "bearbeiten"], kunden: ["sehen"] }),
  custom_verwalter: nutzer("custom", ALLES, { darf_zeiten_buchen: true, darf_abwesenheiten_verwalten: true }),
  custom_module_aus: nutzer("custom", ALLES, {
    deaktivierte_module: ["dispo", "material", "abrechnung", "zeiterfassung", "postfach", "highlights", "statistik", "pruefzyklen", "nachunternehmer"] as MandantModul[],
  }),
};

function backendErlaubt(key: string, n: Nutzer): boolean {
  const gate = BACKEND[key];
  if (!gate) return false;
  const rolleOk = gate.rollen.includes(n.role) || (n.role === "loesch_operativ" && gate.rollen.includes("mandant_admin"));
  if (!rolleOk) return false;
  // require_recht greift nur bei custom; die anderen Rollen haben ohnehin alle Rechte.
  const hat = ([b, a]: [RechteBereich, RechteAktion]) => n.role !== "custom" || (n.rechte[b]?.includes(a) ?? false);
  if (gate.recht && !gate.recht.every(hat)) return false;
  if (gate.rechteOder && n.role === "custom" && !gate.rechteOder.some(hat)) return false;
  if (gate.modul && n.deaktivierte_module.includes(gate.modul)) return false;
  return gate.extra ? gate.extra(n) : true;
}

function sichtbar(n: Nutzer, oberflaeche: "office" | "feld" = "office") {
  const hatRecht = (b: RechteBereich, a: RechteAktion) => n.rechte[b]?.includes(a) ?? false;
  const seiten = sichtbareNavSeiten(n as unknown as CurrentUser, hatRecht, oberflaeche);
  // Wie pages/feld/MehrPage.tsx: dort werden nurOffice-Seiten ausgeblendet.
  return oberflaeche === "feld" ? seiten.filter((s) => !s.nurOffice) : seiten;
}

function routenAus(datei: string): Set<string> {
  const quelle = readFileSync(join(__dirname, "..", datei), "utf-8");
  return new Set([...quelle.matchAll(/<Route\s+path="([^"]+)"/g)].map((m) => m[1]));
}

describe("NAV_SEITEN: Routen", () => {
  const officeRouten = routenAus("office/OfficeApp.tsx");
  const feldRouten = routenAus("App.tsx");

  it("Schluessel sind eindeutig und jeder hat einen Backend-Soll-Eintrag", () => {
    const keys = NAV_SEITEN.map((s) => s.key);
    expect(new Set(keys).size).toBe(keys.length);
    expect(keys.filter((k) => !(k in BACKEND))).toEqual([]);
    expect(Object.keys(BACKEND).filter((k) => !keys.includes(k))).toEqual([]);
  });

  it("jede Office-Seite hat eine Route in OfficeApp.tsx", () => {
    const fehlend = NAV_SEITEN.filter((s) => !s.nurFeld && !officeRouten.has(s.route)).map((s) => `${s.key} -> ${s.route}`);
    expect(fehlend).toEqual([]);
  });

  it("jede Feld-Seite hat eine Route in App.tsx", () => {
    const fehlend = NAV_SEITEN.filter((s) => !s.nurOffice && !feldRouten.has(s.route)).map((s) => `${s.key} -> ${s.route}`);
    expect(fehlend).toEqual([]);
  });

  it("nurOffice und nurFeld schliessen sich aus", () => {
    expect(NAV_SEITEN.filter((s) => s.nurOffice && s.nurFeld)).toEqual([]);
  });
});

describe("NAV_SEITEN: Sichtbarkeit je Rolle", () => {
  for (const [name, n] of Object.entries(NUTZER)) {
    for (const oberflaeche of ["office", "feld"] as const) {
      it(`${name} (${oberflaeche}) sieht nur Seiten, die das Backend freigibt`, () => {
        const unerlaubt = sichtbar(n, oberflaeche)
          .map((s) => s.key)
          .filter((k) => !backendErlaubt(k, n));
        expect(unerlaubt).toEqual([]);
      });
    }
  }

  it("mandant_admin findet alle Office-Seiten, die sein Backend erlaubt", () => {
    const n = NUTZER.mandant_admin;
    const erwartet = NAV_SEITEN.filter((s) => !s.nurFeld && backendErlaubt(s.key, n)).map((s) => s.key);
    expect(sichtbar(n).map((s) => s.key).sort()).toEqual(erwartet.sort());
    // Neue Seiten muessen auffindbar sein, nicht nur ueber die URL erreichbar.
    for (const key of ["protokoll", "datenimport", "export", "postfach"]) {
      expect(sichtbar(n).map((s) => s.key)).toContain(key);
    }
  });

  it("loesch_operativ sieht Datenimport, aber weder Protokoll noch Export", () => {
    const keys = sichtbar(NUTZER.loesch_operativ).map((s) => s.key);
    expect(keys).toContain("datenimport");
    expect(keys).not.toContain("protokoll");
    expect(keys).not.toContain("export");
  });

  it("loesch_ansicht sieht nur Papierkorb und Profil", () => {
    expect(sichtbar(NUTZER.loesch_ansicht).map((s) => s.key).sort()).toEqual(["papierkorb", "profil"]);
  });

  it("ein custom-Nutzer ohne Rechte sieht keine Verwaltungsseiten", () => {
    const keys = sichtbar(NUTZER.custom_ohne_rechte).map((s) => s.key);
    for (const key of ["nutzer", "account_typen", "integrationen", "protokoll", "datenimport", "export", "kennzahlen", "anlagen_felder"]) {
      expect(keys).not.toContain(key);
    }
  });

  it("Admin-Seiten (Protokoll, Datenimport, Export) tauchen nie in der Feld-App auf", () => {
    const keys = sichtbar(NUTZER.mandant_admin, "feld").map((s) => s.key);
    for (const key of ["protokoll", "datenimport", "export"]) expect(keys).not.toContain(key);
  });
});
