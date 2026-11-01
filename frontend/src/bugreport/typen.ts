export interface NetzwerkEintrag {
  zeit: string;
  methode: string;
  url: string;
  status: number;
  dauer_ms: number;
  fehler?: string;
  request_headers?: Record<string, string>;
  response_headers?: Record<string, string>;
  request_body?: string;
  response_body?: string;
}

export interface KonsolenEintrag {
  zeit: string;
  level: "error" | "warn" | "log";
  nachricht: string;
  stack?: string;
}

export interface Breadcrumb {
  zeit: string;
  typ: "route" | "klick" | "submit";
  ziel: string;
  text?: string;
}

export interface Umgebung {
  url: string;
  route: string;
  app_version: string;
  commit_sha: string;
  userAgent: string;
  plattform: string;
  viewport: { breite: number; hoehe: number; dpr: number };
  sprache: string;
  zeitzone: string;
  online: boolean;
  zeit: string;
}

export interface Sitzung {
  user_id?: string;
  mandant_id?: string;
  rolle?: string;
  flags?: string[];
}

export type Kategorie = "netzwerk" | "konsole" | "breadcrumbs" | "umgebung" | "sitzung" | "app_state";

export interface FehlerberichtKontext {
  netzwerk?: NetzwerkEintrag[];
  konsole?: KonsolenEintrag[];
  breadcrumbs?: Breadcrumb[];
  umgebung?: Umgebung;
  sitzung?: Sitzung;
  app_state?: Record<string, unknown>;
}
