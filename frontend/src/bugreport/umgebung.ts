import { maskiereMuster, schwaerzeUrl, STANDARD_CONFIG, type SchwaerzConfig } from "./schwaerzen";
import type { Umgebung } from "./typen";

export function erfasseUmgebung(opt: {
  appVersion: string;
  commitSha: string;
  schwaerz?: SchwaerzConfig;
}): Umgebung {
  const nav = navigator as Navigator & { userAgentData?: { platform?: string } };
  let zeitzone = "";
  try {
    zeitzone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    // Intl nicht verfuegbar
  }
  return {
    url: schwaerzeUrl(location.href, opt.schwaerz ?? STANDARD_CONFIG),
    route: maskiereMuster(location.pathname, opt.schwaerz ?? STANDARD_CONFIG, false),
    app_version: opt.appVersion,
    commit_sha: opt.commitSha,
    userAgent: nav.userAgent,
    plattform: nav.userAgentData?.platform ?? nav.platform ?? "",
    viewport: { breite: window.innerWidth, hoehe: window.innerHeight, dpr: window.devicePixelRatio || 1 },
    sprache: nav.language,
    zeitzone,
    online: nav.onLine,
    zeit: new Date().toISOString(),
  };
}
