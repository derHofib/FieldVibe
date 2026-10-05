import type { RechteRegistry } from "../types/organigramm";

// Systemvorlagen fuer Account-Typen ("Vorlage anlegen" in pages/AccountTypenPage.tsx).
// Es gibt dafuer bewusst keinen Backend-Endpunkt: eine Vorlage legt ueber die bestehenden APIs
// einen normalen Account-Typ an (POST /api/account-typen) und setzt die Rechte einzeln
// (PUT /api/account-typen/{id}/rechte). Danach ist der Typ ein gewoehnlicher, frei aenderbarer Typ.
//
// Rechte-Sets sind Bereich -> Stufe bzw. explizite Aktionsliste. Maßgeblich ist die Registry: Aktionen,
// die sie fuer einen Bereich nicht kennt (z. B. exportieren in einem kuenftig schmaleren Bereich),
// werden beim Expandieren verworfen. Die Reichweite (Scope) setzt das Backend beim Anlegen selbst
// ("eigene" bei nur_zugewiesene_kunden, sonst "mandant"); die Vorlage kann sie nicht beeinflussen.

export type RechteStufe =
  | "lesen" // sehen
  | "standard" // sehen, erstellen, bearbeiten
  | "ohne_verwaltung" // alles ausser rechte_verwalten
  | "alle"; // alle Aktionen des Bereichs

export type RechteSet = Record<string, RechteStufe | string[]>;

export interface AccountTypVorlage {
  key: string;
  name: string;
  beschreibung: string;
  flags: {
    nur_zugewiesene_kunden: boolean;
    darf_vorgaenge_selbst_uebernehmen: boolean;
    darf_zeiten_buchen: boolean;
    darf_abwesenheiten_verwalten: boolean;
  };
  // Bereiche, die hier nicht vorkommen, bleiben ohne Recht.
  rechte: RechteSet;
}

const KEINE_FLAGS = {
  nur_zugewiesene_kunden: false,
  darf_vorgaenge_selbst_uebernehmen: false,
  darf_zeiten_buchen: false,
  darf_abwesenheiten_verwalten: false,
};

/** Alle Bereiche mit derselben Stufe -- Hilfsfunktion fuer Geschaeftsfuehrer/Admin. */
function ueberall(stufe: RechteStufe, bereiche: string[]): RechteSet {
  return Object.fromEntries(bereiche.map((b) => [b, stufe]));
}

const ALLE_BEREICHE = [
  "vorgaenge",
  "kunden",
  "material",
  "dispo",
  "abrechnung",
  "statistik",
  "mitarbeiterverwaltung",
  "formulare",
  "partner",
  "projekte",
  "fehlerberichte",
  "organigramm",
];

export const ACCOUNT_TYP_VORLAGEN: AccountTypVorlage[] = [
  {
    key: "geschaeftsfuehrer",
    name: "Geschäftsführer",
    beschreibung: "Voller Zugriff in allen Bereichen inkl. Rechteverwaltung; verwaltet Abwesenheiten.",
    flags: { ...KEINE_FLAGS, darf_abwesenheiten_verwalten: true },
    rechte: ueberall("alle", ALLE_BEREICHE),
  },
  {
    key: "bereichsleiter",
    name: "Bereichsleiter",
    beschreibung: "Fachbereiche vollständig, Personal und Organigramm mit Rechteverwaltung (im eigenen Verantwortungsbereich).",
    flags: { ...KEINE_FLAGS, darf_vorgaenge_selbst_uebernehmen: true, darf_abwesenheiten_verwalten: true },
    rechte: {
      ...ueberall("ohne_verwaltung", ["vorgaenge", "kunden", "material", "dispo", "abrechnung", "statistik", "partner", "projekte"]),
      mitarbeiterverwaltung: ["sehen", "bearbeiten", "rechte_verwalten"],
      organigramm: ["sehen", "erstellen", "bearbeiten", "rechte_verwalten"],
      formulare: "standard",
      fehlerberichte: "standard",
    },
  },
  {
    key: "teamleiter",
    name: "Teamleiter",
    beschreibung: "Arbeitet operativ (Aufträge, Dispo, Kunden, Projekte), sieht Team und Organigramm lesend.",
    flags: { ...KEINE_FLAGS, darf_vorgaenge_selbst_uebernehmen: true, darf_zeiten_buchen: true },
    rechte: {
      vorgaenge: "standard",
      kunden: "standard",
      dispo: "standard",
      projekte: ["sehen", "erstellen", "bearbeiten", "zeitplan_sehen", "zeitplan_beantragen"],
      material: "lesen",
      mitarbeiterverwaltung: "lesen",
      organigramm: "lesen",
      fehlerberichte: "standard",
    },
  },
  {
    key: "mitarbeiter",
    name: "Mitarbeiter",
    beschreibung: "Techniker im Feld: eigene Aufträge, nur zugewiesene Kunden, Zeitplan lesen und Änderungen beantragen.",
    flags: { ...KEINE_FLAGS, nur_zugewiesene_kunden: true, darf_vorgaenge_selbst_uebernehmen: true },
    rechte: {
      vorgaenge: "standard",
      kunden: "lesen",
      material: "lesen",
      dispo: "lesen",
      projekte: ["zeitplan_sehen", "zeitplan_beantragen"],
      fehlerberichte: ["sehen", "erstellen"],
    },
  },
  {
    key: "stabsstelle",
    name: "Stabsstelle",
    beschreibung: "Lesender Überblick mit Export (z. B. Controlling, QM, Datenschutz), ohne Änderungsrechte.",
    flags: KEINE_FLAGS,
    rechte: {
      vorgaenge: ["sehen", "exportieren"],
      kunden: ["sehen", "exportieren"],
      abrechnung: ["sehen", "exportieren"],
      statistik: ["sehen", "exportieren"],
      projekte: ["sehen", "exportieren"],
      dispo: "lesen",
      material: "lesen",
      mitarbeiterverwaltung: "lesen",
      organigramm: "lesen",
    },
  },
  {
    key: "admin",
    name: "Admin",
    beschreibung: "Alle Rechte und alle Zusatzoptionen (Selbst übernehmen, Zeiten buchen, Abwesenheiten). Kein Ersatz für die Rolle mandant_admin.",
    flags: {
      nur_zugewiesene_kunden: false,
      darf_vorgaenge_selbst_uebernehmen: true,
      darf_zeiten_buchen: true,
      darf_abwesenheiten_verwalten: true,
    },
    rechte: ueberall("alle", ALLE_BEREICHE),
  },
];

function stufeAktionen(stufe: RechteStufe, aktionen: string[]): string[] {
  switch (stufe) {
    case "lesen":
      return ["sehen"];
    case "standard":
      return ["sehen", "erstellen", "bearbeiten"];
    case "ohne_verwaltung":
      return aktionen.filter((a) => a !== "rechte_verwalten");
    case "alle":
      return aktionen;
  }
}

/** Konkrete (Bereich, Aktion)-Paare einer Vorlage, begrenzt auf das, was die Registry kennt. */
export function vorlagenRechte(vorlage: AccountTypVorlage, registry: RechteRegistry): { bereich: string; aktion: string }[] {
  const ergebnis: { bereich: string; aktion: string }[] = [];
  for (const b of registry.bereiche) {
    const spec = vorlage.rechte[b.key];
    if (!spec) continue;
    const gewuenscht = Array.isArray(spec) ? spec : stufeAktionen(spec, b.aktionen);
    for (const aktion of b.aktionen) {
      if (gewuenscht.includes(aktion)) ergebnis.push({ bereich: b.key, aktion });
    }
  }
  return ergebnis;
}
