import { matchPath } from "react-router-dom";

import type { CurrentUser, RechteAktion, RechteBereich } from "../types";
import { istModulAktiv } from "../utils/module";
import { istAdminOderCustom } from "../utils/rollen";
import { NAV_SEITEN } from "./navSeiten";

export interface RoutenKontext {
  currentUser: CurrentUser | undefined;
  hatRecht: (bereich: RechteBereich, aktion: RechteAktion) => boolean;
  // Die Feld-App kennt fuer /projekte zusaetzlich die Zeitplan-Ansicht
  // (ProjektePageMobil), das Office-Kanban nicht.
  oberflaeche?: "office" | "feld";
}

type Pruefung = (ctx: RoutenKontext) => boolean;

interface RoutenRegel {
  muster: string;
  // true: gilt auch fuer alle Unterpfade (/kunden -> /kunden/:id).
  mitUnterpfaden?: boolean;
  pruefe: Pruefung;
}

// Reihenfolge = Vorrang: die erste passende Regel entscheidet, deshalb stehen
// spezifische Unterpfade vor ihrem Praefix (/einstellungen/export vor /einstellungen).
// Backend-Gegenstuecke stehen in den Kommentaren der Nav-Eintraege (navSeiten.ts)
// bzw. direkt hier fuer Routen ohne Menueeintrag.
const SONDERREGELN: RoutenRegel[] = [
  {
    muster: "/projekte",
    mitUnterpfaden: true,
    pruefe: ({ hatRecht, oberflaeche }) =>
      hatRecht("projekte", "sehen") || (oberflaeche !== "office" && hatRecht("projekte", "zeitplan_sehen")),
  },
  // Ohne Menueeintrag
  {
    muster: "/plan-symbole",
    pruefe: ({ currentUser, hatRecht }) => istAdminOderCustom(currentUser) && hatRecht("formulare", "sehen"),
  },
  {
    muster: "/form-submissions/:id",
    pruefe: ({ currentUser, hatRecht }) => istAdminOderCustom(currentUser) && hatRecht("vorgaenge", "sehen"),
  },
  {
    muster: "/anlagen/:id",
    pruefe: ({ hatRecht }) => hatRecht("kunden", "sehen"),
  },
  {
    muster: "/angebote",
    mitUnterpfaden: true,
    pruefe: (ctx) => nutzeNavRegel("rechnungen", ctx),
  },
  {
    muster: "/bestellungen",
    mitUnterpfaden: true,
    pruefe: (ctx) => nutzeNavRegel("material", ctx),
  },
  {
    muster: "/fehlerberichte",
    mitUnterpfaden: true,
    pruefe: ({ hatRecht }) => hatRecht("fehlerberichte", "sehen"),
  },
  // Wie die Seiten selbst: strikt mandant_admin (Backend nur_mandant_admin bzw. Seitenlogik).
  {
    muster: "/einstellungen/export",
    pruefe: ({ currentUser }) => currentUser?.role === "mandant_admin",
  },
  {
    muster: "/einstellungen/kategorien",
    pruefe: ({ currentUser }) => currentUser?.role === "mandant_admin",
  },
  {
    muster: "/einstellungen/arbeitszeit",
    pruefe: ({ currentUser }) =>
      !!currentUser?.darf_abwesenheiten_verwalten && istModulAktiv(currentUser, "zeiterfassung"),
  },
  // Custom-Rolle darf die Einstellungsseite oeffnen; die Unterbereiche blendet
  // SettingsPage selbst nach Rolle/Recht aus.
  {
    muster: "/einstellungen",
    mitUnterpfaden: true,
    pruefe: ({ currentUser }) => istAdminOderCustom(currentUser),
  },
];

function nutzeNavRegel(key: string, ctx: RoutenKontext): boolean {
  const seite = NAV_SEITEN.find((s) => s.key === key);
  return seite ? seite.sichtbar(ctx) : true;
}

// "zeitplaene" teilt sich /projekte mit "projekte" und ist oben abgedeckt.
const NAV_REGELN: RoutenRegel[] = NAV_SEITEN.filter((s) => s.key !== "zeitplaene").map((s) => ({
  muster: s.route,
  mitUnterpfaden: true,
  pruefe: (ctx) => s.sichtbar(ctx),
}));

export const ROUTEN_REGELN: RoutenRegel[] = [...SONDERREGELN, ...NAV_REGELN];

/** Unbekannte Pfade ohne Regel (Detailseiten ohne eigenes Recht, /mehr, /neu ...) bleiben offen. */
export function routeErlaubt(pfad: string, ctx: RoutenKontext): boolean {
  const regel = ROUTEN_REGELN.find((r) => matchPath({ path: r.muster, end: !r.mitUnterpfaden }, pfad));
  return regel ? regel.pruefe(ctx) : true;
}
