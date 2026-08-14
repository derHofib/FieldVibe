/** Erkennung der Desktop-Oberflaeche. Bewusst am Hostname statt an einem
 * eigenen Build-Entry: beide Subdomains werden vom selben Container und
 * demselben `serve -s dist` ausgeliefert (siehe Caddyfile), das jeden
 * unbekannten Pfad auf index.html umschreibt, ohne den Host anzusehen. */

const OFFICE_PRAEFIX = "office.";

/** Lokal gibt es keine office.-Subdomain. `?office=1` schaltet die Oberflaeche
 * fuer die Sitzung frei (in sessionStorage gemerkt, damit sie beim Navigieren
 * innerhalb der App nicht wieder verloren geht), `?office=0` wieder ab. */
const DEV_FLAG_KEY = "fieldvibe-office-dev";

export function istOfficeHost(): boolean {
  if (typeof window === "undefined") return false;

  const param = new URLSearchParams(window.location.search).get("office");
  if (param === "1" || param === "0") {
    try {
      if (param === "1") sessionStorage.setItem(DEV_FLAG_KEY, "1");
      else sessionStorage.removeItem(DEV_FLAG_KEY);
    } catch {
      // Privater Modus o. ae. -- der Parameter wirkt dann nur fuer diesen
      // Seitenaufruf, das reicht zum Anschauen.
    }
    return param === "1";
  }

  try {
    if (sessionStorage.getItem(DEV_FLAG_KEY) === "1") return true;
  } catch {
    // ignorieren, siehe oben
  }

  return window.location.hostname.startsWith(OFFICE_PRAEFIX);
}

/** Adresse derselben Seite auf der Handy-Subdomain, oder null wenn es keine
 * gibt (lokal, IP-Deployment). Pfad und Query bleiben erhalten. */
export function mobileUrl(): string | null {
  if (typeof window === "undefined") return null;
  const host = window.location.hostname;
  if (!host.startsWith(OFFICE_PRAEFIX)) return null;
  const url = new URL(window.location.href);
  url.hostname = `app.${host.slice(OFFICE_PRAEFIX.length)}`;
  url.searchParams.delete("office");
  return url.toString();
}
