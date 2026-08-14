/** Automatische Weiterleitung zwischen Handy- und Desktop-Oberflaeche anhand
 * der Fensterbreite. Laeuft einmal beim Start, bevor React rendert. */

/** Unterhalb dieser Breite ist die Desktop-Oberflaeche (Sidebar + Tabellen)
 * nicht mehr sinnvoll bedienbar. Bewusst deutlich unter typischen
 * Tablet-Querformat-Breiten, damit ein iPad nicht auf die Handy-Ansicht
 * geworfen wird. */
const SCHWELLE_PX = 900;

/** Verhindert eine Endlosschleife und respektiert eine bewusste Entscheidung:
 * Wer den "Zur mobilen Ansicht"-Link klickt, soll nicht sofort
 * zurueckgeworfen werden. Gilt pro Tab. */
const STOPP_KEY = "fieldvibe-weiche-aus";

export function weicheAus(): void {
  try {
    sessionStorage.setItem(STOPP_KEY, "1");
  } catch {
    // ignorieren -- ohne sessionStorage greift die Weiche halt wieder
  }
}

function weicheAbgeschaltet(): boolean {
  try {
    return sessionStorage.getItem(STOPP_KEY) === "1";
  } catch {
    return false;
  }
}

function ersetzeSubdomain(host: string, neu: string): string | null {
  const punkt = host.indexOf(".");
  // Nur echte Subdomains umschreiben. "localhost" oder eine nackte IP haben
  // keine, dort gibt es nichts umzuleiten.
  if (punkt <= 0) return null;
  const rest = host.slice(punkt + 1);
  if (!rest.includes(".")) return null;
  return `${neu}.${rest}`;
}

/**
 * @param istOffice ob die Seite gerade als Desktop-Oberflaeche laeuft
 * @returns true, wenn eine Weiterleitung ausgeloest wurde (Aufrufer sollte
 *          dann nicht mehr rendern)
 */
export function pruefeGeraeteWeiche(istOffice: boolean): boolean {
  if (typeof window === "undefined") return false;
  if (weicheAbgeschaltet()) return false;

  // Das Kundenportal ist eine eigene Anwendung fuer Endkunden -- die sind
  // typischerweise am Handy und duerfen niemals auf eine Buero-Oberflaeche
  // umgeleitet werden.
  if (window.location.pathname.startsWith("/portal")) return false;

  const breit = window.innerWidth >= SCHWELLE_PX;
  if (istOffice === breit) return false;

  const ziel = ersetzeSubdomain(window.location.hostname, breit ? "office" : "app");
  if (!ziel || ziel === window.location.hostname) return false;

  const url = new URL(window.location.href);
  url.hostname = ziel;
  // Pfad und Query bleiben erhalten; replace statt assign, damit der
  // Zurueck-Button nicht in einer Weiterleitungsschleife haengen bleibt.
  window.location.replace(url.toString());
  return true;
}
