export type RechtlicheSeite = "impressum" | "datenschutz" | "barrierefreiheit";

export const PORTAL_SLUG_QUERY = "portal_slug";

/** Nur http(s) mit Host -- die URL landet ungeprueft als href, ein
 * javascript:-Wert waere ein XSS-Vektor. */
export function istHttpUrl(wert: string | null | undefined): boolean {
  const url = wert?.trim();
  if (!url || /\s/.test(url)) return false;
  try {
    const u = new URL(url);
    return (u.protocol === "http:" || u.protocol === "https:") && u.host !== "";
  } catch {
    return false;
  }
}

export interface AufgeloesterRechtLink {
  href: string;
  /** true = fremde URL (neuer Tab), false = interne Platzhalter-Route. */
  extern: boolean;
}

/** Reihenfolge je Link: URL aus den Firmendaten > Build-Env > interne
 * Platzhalter-Route. Ungueltige (nicht-http) Werte zaehlen als nicht gesetzt. */
export function aufloesenRechtlicheUrl(opts: {
  seite: RechtlicheSeite;
  firmendatenUrl?: string | null;
  envUrl?: string | null;
  portalSlug?: string | null;
}): AufgeloesterRechtLink {
  const { seite, firmendatenUrl, envUrl, portalSlug } = opts;
  if (istHttpUrl(firmendatenUrl)) return { href: firmendatenUrl!.trim(), extern: true };
  if (istHttpUrl(envUrl)) return { href: envUrl!.trim(), extern: true };
  const query = portalSlug ? `?${PORTAL_SLUG_QUERY}=${encodeURIComponent(portalSlug)}` : "";
  return { href: `/${seite}${query}`, extern: false };
}
