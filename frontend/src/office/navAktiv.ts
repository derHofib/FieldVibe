import type { NavSeite } from "../config/navSeiten";

/** Die Office-Seitenleiste zeigt die Vorgangsliste unter ihrem eigenen Namen.
 * In config/navSeiten.ts heißt der Eintrag "Feed" und zeigt auf /feed (die
 * Handy-Startseite); im Office leitet /feed nur auf /vorgaenge um, ein Link
 * dorthin wäre daher nie als aktiv erkennbar. */
export function fuerOffice(seiten: NavSeite[]): NavSeite[] {
  return seiten.map((seite) =>
    seite.key === "feed"
      ? { ...seite, label: "Vorgänge", route: "/vorgaenge", kategorie: "Arbeit" }
      : seite,
  );
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
