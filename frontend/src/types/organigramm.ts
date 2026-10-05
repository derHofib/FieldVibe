import type { RechteScope } from "./index";

// Spiegelt backend/app/schemas/organigramm.py und schemas/rechte.py.
// Bereiche/Aktionen sind hier bewusst nur `string`: sie kommen aus der Registry
// (GET /api/rechte/registry), nicht aus einer festen Liste im Frontend.

export type PositionTyp = "linie" | "stabsstelle";
export type PositionStatus = "besetzt" | "vakant" | "geplant";
export type BesetzungArt = "regulaer" | "vertretung";
export type OrgEinheitTyp = "bereich" | "abteilung" | "team";
export type RechtWirkung = "erlauben" | "verweigern";

export interface RegistryBereich {
  key: string;
  label: string;
  aktionen: string[];
  scopes: RechteScope[];
  modul: string | null;
}

export interface RechteRegistry {
  bereiche: RegistryBereich[];
  scopes: RechteScope[];
}

export interface OrgEinheitRef {
  id: string;
  name: string;
  typ: string;
}

export interface AccountTypRef {
  id: string;
  name: string;
}

// user_id/name fehlen bzw. sind null, wenn der Abrufer die Person nicht sehen darf (DSGVO).
export interface Besetzung {
  id: string;
  user_id?: string;
  name?: string | null;
  art: BesetzungArt;
  gueltig_von: string;
  gueltig_bis: string | null;
}

// kontext=true: nur Pfad zur Wurzel, alle Detailfelder fehlen.
export interface Position {
  id: string;
  parent_id: string | null;
  titel: string;
  typ: PositionTyp;
  kontext?: boolean;
  ist_ausser_linie?: boolean;
  status?: PositionStatus;
  ebene?: number | null;
  org_einheit?: OrgEinheitRef | null;
  account_typ?: AccountTypRef | null;
  geplant?: boolean;
  soll_besetzung?: number;
  ist_besetzung?: number;
  gueltig_ab?: string | null;
  gueltig_bis?: string | null;
  archiviert_am?: string | null;
  reihenfolge?: number;
  besetzungen?: Besetzung[];
}

export interface RechtOverride {
  bereich: string;
  aktion: string;
  wirkung: RechtWirkung;
  scope: RechteScope | null;
}

// herkunft: {art: "account_typ" | "position_override" | "user_override", ...}
export interface HerkunftEintrag {
  art: string;
  wirkung?: string;
  account_typ_id?: string;
  position_id?: string;
}

export interface EffektivesRecht {
  bereich: string;
  aktion: string;
  scope: RechteScope;
  herkunft: HerkunftEintrag[];
}

export interface RechtDiff {
  bereich: string;
  aktion: string;
  art: "hinzugefuegt" | "entfernt" | "scope_geaendert";
  typ_scope: RechteScope | null;
  position_scope: RechteScope | null;
}

export interface PositionDetail extends Position {
  alle_besetzungen: Besetzung[];
  overrides: RechtOverride[];
  effektive_rechte: EffektivesRecht[];
  diff_zur_vorlage: RechtDiff[];
  unterpositionen: number;
}

export interface PositionCreate {
  parent_id: string;
  typ?: PositionTyp;
  titel: string;
  ebene?: number | null;
  org_einheit_id?: string | null;
  account_typ_id?: string | null;
  geplant?: boolean;
  soll_besetzung?: number;
  gueltig_ab?: string | null;
  gueltig_bis?: string | null;
  reihenfolge?: number;
}

export type PositionUpdate = Partial<Omit<PositionCreate, "parent_id">> & { parent_id?: string | null };

export interface BesetzungCreate {
  user_id: string;
  art?: BesetzungArt;
  gueltig_von?: string | null;
  gueltig_bis?: string | null;
}

export interface BesetzungErgebnis {
  besetzung: Besetzung;
  warnung?: string | null;
}

export interface RechtOverrideIn {
  bereich: string;
  aktion: string;
  wirkung: RechtWirkung;
  scope?: RechteScope | null;
}

export interface EffektivRead {
  user_id: string | null;
  position_id: string | null;
  rolle: string | null;
  alle_rechte: boolean;
  rechte: EffektivesRecht[];
  verweigert: { bereich: string; aktion: string; herkunft: HerkunftEintrag[] }[];
}

export interface OrgEinheit {
  id: string;
  name: string;
  typ: OrgEinheitTyp;
  parent_id: string | null;
  archiviert_am: string | null;
}
