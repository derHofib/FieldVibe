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

export type KiAktionStatus =
  | "ausgefuehrt"
  | "vorgeschlagen"
  | "abgelehnt"
  | "verfallen"
  | "fehlgeschlagen"
  | "rueckgaengig";

export type KiObjektTyp =
  | "vorgang"
  | "auftrag"
  | "projekt"
  | "aufgabe"
  | "kunde"
  | "standort"
  | "anlage"
  | "kontakt_vor_ort"
  | "termin"
  | "telefonat"
  | "mangel"
  | "formular"
  | "vorlage"
  | "kommentar";

export interface KiObjektRef {
  typ: KiObjektTyp | string;
  id: string;
  label: string;
}

export interface KiAenderung {
  typ: string;
  id: string;
  label: string;
  feld: string;
  feld_label: string;
  vorher: string | null;
  nachher: string | null;
}

export interface KiAktion {
  id: string;
  user_id: string;
  user_name: string;
  ki_verbindung_id: string | null;
  client_name: string | null;
  tool: string;
  aktionsart: string;
  stufe: 1 | 2 | 3;
  status: KiAktionStatus;
  zusammenfassung: string;
  ziele: KiObjektRef[];
  erzeugt: KiObjektRef[];
  aenderungen: KiAenderung[];
  rueckgaengig_moeglich: boolean;
  rueckgaengig_bis: string | null;
  rueckgaengig_am: string | null;
  rueckgaengig_von_name: string | null;
  fehler: string | null;
  erstellt_am: string;
}

export interface KiAktionenListe {
  eintraege: KiAktion[];
  gesamt: number;
}

export interface KiAktionenFilter {
  status?: string;
  user_id?: string;
  von?: string;
  bis?: string;
  q?: string;
}

export interface KiRueckgaengigKonflikt {
  label: string;
  feld_label: string;
  erwartet_anzeige: string | null;
  aktuell_anzeige: string | null;
}
