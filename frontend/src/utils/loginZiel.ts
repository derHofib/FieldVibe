// Ziel, auf das nach dem Login zurueckgeleitet wird (z. B. die Einwilligungsseite
// der KI-Anbindung, die ein externer Client mit Query aufruft).
const SCHLUESSEL = "login.ziel";
const GUELTIG_MS = 10 * 60 * 1000;

/** Nur relative Pfade innerhalb der App: "//host" und "/\host" wuerden vom Browser
 * als fremder Host gelesen (offener Redirect). */
export function istSicheresLoginZiel(ziel: unknown): ziel is string {
  return (
    typeof ziel === "string" &&
    ziel.startsWith("/") &&
    !ziel.startsWith("//") &&
    !ziel.startsWith("/\\") &&
    !/^\/(login|registrieren|passwort-)/.test(ziel)
  );
}

export function merkeLoginZiel(ziel: string): void {
  if (!istSicheresLoginZiel(ziel) || ziel === "/") return;
  try {
    sessionStorage.setItem(SCHLUESSEL, JSON.stringify({ ziel, bis: Date.now() + GUELTIG_MS }));
  } catch {
    /* sessionStorage gesperrt: Login landet dann auf der Startseite */
  }
}

export function holeLoginZiel(): string | null {
  try {
    const roh = sessionStorage.getItem(SCHLUESSEL);
    if (!roh) return null;
    const { ziel, bis } = JSON.parse(roh) as { ziel?: unknown; bis?: unknown };
    if (typeof bis !== "number" || bis < Date.now() || !istSicheresLoginZiel(ziel)) return null;
    return ziel;
  } catch {
    return null;
  }
}

export function loescheLoginZiel(): void {
  try {
    sessionStorage.removeItem(SCHLUESSEL);
  } catch {
    /* s. o. */
  }
}
