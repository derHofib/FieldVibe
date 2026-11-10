import { Package, Users } from "lucide-react";

import type { NavSeite } from "../config/navSeiten";
import { istModulAktiv } from "../utils/module";

// Nur im Office: Kunden und Material haben dort eigene Desktop-Seiten
// (office/kunden, office/material). In der Handy-App stecken sie weiter als
// Tabs in "Geschäft" -- deshalb leben die Einträge hier und nicht in
// config/navSeiten.ts. Rechte/Module wie die Tabs in GeschaeftPage.
const OFFICE_ZUSATZ_SEITEN: NavSeite[] = [
  {
    key: "kunden",
    label: "Kunden",
    icon: Users,
    tone: "emerald",
    route: "/kunden",
    kategorie: "Arbeit",
    sichtbar: ({ currentUser, hatRecht }) =>
      hatRecht("kunden", "sehen") && istModulAktiv(currentUser, "kundenverwaltung"),
  },
  {
    key: "material",
    label: "Material",
    icon: Package,
    tone: "amber",
    route: "/material",
    kategorie: "Arbeit",
    sichtbar: ({ currentUser, hatRecht }) =>
      hatRecht("material", "sehen") && istModulAktiv(currentUser, "material"),
  },
];

export const OFFICE_ZUSATZ_KEYS = OFFICE_ZUSATZ_SEITEN.map((s) => s.key);

/** Die Office-Seitenleiste zeigt die Vorgangsliste unter ihrem eigenen Namen.
 * In config/navSeiten.ts heißt der Eintrag "Feed" und zeigt auf /feed (die
 * Handy-Startseite); im Office leitet /feed nur auf /vorgaenge um, ein Link
 * dorthin wäre daher nie als aktiv erkennbar. Kunden und Material werden
 * direkt hinter "Geschäft" eingefügt. */
export function fuerOffice(seiten: NavSeite[], ctx?: Parameters<NavSeite["sichtbar"]>[0]): NavSeite[] {
  const zusatz = ctx ? OFFICE_ZUSATZ_SEITEN.filter((s) => s.sichtbar(ctx)) : [];
  return seiten.flatMap((seite) => {
    if (seite.key === "feed") {
      return [{ ...seite, label: "Vorgänge", route: "/vorgaenge", kategorie: "Arbeit" as const }];
    }
    return seite.key === "geschaeft" ? [seite, ...zusatz] : [seite];
  });
}

// Unterseiten, die zu einem Eintrag gehören, aber nicht unter dessen Route
// liegen (Angebote hängen an "Rechnungen", Neuanlage an "Vorgänge" usw.).
const ROUTEN_ZUORDNUNG: [route: string, key: string][] = [
  ["/neu", "feed"],
  ["/vorgang-formulare", "feed"],
  ["/dauerauftraege", "feed"],
  ["/angebote", "rechnungen"],
  ["/bestellungen", "geschaeft"],
  ["/standorte", "kunden"],
  ["/anlagen", "kunden"],
  ["/einstellungen", "profil"],
];

function liegtUnter(pfad: string, route: string): boolean {
  return pfad === route || pfad.startsWith(`${route}/`);
}

/** Bestimmt den markierten Eintrag allein aus dem Pfad -- so stimmt die
 * Markierung auch nach Reload und bei Deep-Links. null, wenn kein sichtbarer
 * Eintrag passt. */
export function aktiverNavKey(pfad: string, seiten: NavSeite[]): string | null {
  const direkt = seiten
    .filter((s) => liegtUnter(pfad, s.route))
    .sort((a, b) => b.route.length - a.route.length)[0];
  if (direkt) return direkt.key;
  const keys = new Set(seiten.map((s) => s.key));
  const zugeordnet = ROUTEN_ZUORDNUNG.find(([route, key]) => keys.has(key) && liegtUnter(pfad, route));
  return zugeordnet?.[1] ?? null;
}
