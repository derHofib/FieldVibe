import { seiteInWorkspace, type NavSeite, type Workspace } from "../config/navSeiten";

/** Die Office-Seitenleiste zeigt die Vorgangsliste unter ihrem eigenen Namen.
 * In config/navSeiten.ts heißt der Eintrag "Feed" und zeigt auf /feed (die
 * Handy-Startseite); im Office leitet /feed nur auf /vorgaenge um, ein Link
 * dorthin wäre daher nie als aktiv erkennbar. */
export function fuerOffice(seiten: NavSeite[]): NavSeite[] {
  return seiten.map((seite) =>
    seite.key === "feed" ? { ...seite, label: "Vorgänge", route: "/vorgaenge" } : seite,
  );
}

// Unterseiten, die zu einem Eintrag gehören, aber nicht unter dessen Route
// liegen (Angebote hängen an "Rechnungen", Neuanlage an "Vorgänge" usw.).
const ROUTEN_ZUORDNUNG: [route: string, key: string][] = [
  ["/neu", "feed"],
  ["/form-submissions", "feed"],
  ["/dauerauftraege", "feed"],
  ["/angebote", "rechnungen"],
  ["/bestellungen", "material"],
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

/** Workspace folgt der Route: gehört die aktive Seite nicht zum gemerkten
 * Workspace, wird der erste passende gewählt (Deep-Link, Reload, Link aus
 * einer anderen Seite). Gemeinsame Seiten und Seiten ohne Eintrag lassen den
 * gemerkten Workspace unverändert. */
export function workspaceFuerRoute(
  aktiveSeite: NavSeite | undefined,
  workspaces: Workspace[],
  gemerkt: string | null,
): Workspace | undefined {
  const basis = workspaces.find((w) => w.key === gemerkt) ?? workspaces[0];
  if (!aktiveSeite || !basis || seiteInWorkspace(aktiveSeite, basis)) return basis;
  return workspaces.find((w) => seiteInWorkspace(aktiveSeite, w)) ?? basis;
}
