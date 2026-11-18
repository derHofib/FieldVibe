// Vertrag der KI-Anbindung (MCP): Einwilligung und Verbindungsverwaltung.
export type KiScope = "fieldvibe.lesen" | "fieldvibe.schreiben";

export interface KiAnfrage {
  client_name: string;
  scopes_angefragt: KiScope[];
  schreiben_erlaubt: boolean;
  redirect_host: string;
}

export interface KiRedirect {
  redirect_url: string;
}

export interface KiVerbindung {
  id: string;
  client_name: string;
  scopes: KiScope[];
  user_id: string;
  user_name: string;
  erstellt_am: string;
  zuletzt_genutzt_am: string | null;
}
