import { isoDatum, zeitraumAufloesen, zuServerParametern } from "../components/filter/auswerten";
import type { StatusKey } from "../components/apple/status";
import { vorgangStatusZuToken } from "../components/apple/status";
import type { FilterBedingung, FilterOption, FilterWert } from "../components/filter/typen";
import { bedingungenZuUrl } from "../components/filter/url";
import type { VorgangStatus } from "../types";
import { LEISTUNGSTYP_LABEL, STATUS_LABEL } from "./vorgangDarstellung";

/** Gemeinsame Filterlogik von Feed (Feld-App) und Office-Vorgangsliste: beide sprechen `GET /api/feed`. */

export const ALLE_STATUS = Object.keys(STATUS_LABEL) as VorgangStatus[];

export const STATUS_OPTIONEN: FilterOption[] = ALLE_STATUS.map((s) => ({
  wert: s,
  label: STATUS_LABEL[s],
  status: vorgangStatusZuToken(s) as StatusKey,
}));

export const LEISTUNGSTYP_OPTIONEN: FilterOption[] = Object.entries(LEISTUNGSTYP_LABEL).map(([wert, label]) => ({
  wert,
  label,
}));

export const ABRECHNUNGSART_OPTIONEN: FilterOption[] = [
  { wert: "aufwand", label: "Nach Aufwand" },
  { wert: "pauschale", label: "Pauschale" },
  { wert: "festpreis", label: "Festpreis" },
  { wert: "wartungsvertrag", label: "Wartungsvertrag" },
  { wert: "gewaehrleistung", label: "Gewährleistung" },
];

/** Einzige Option des Felds "Zugewiesen an": das Backend kennt nur `nur_meine`, keine fremden Nutzer. */
export const PERSON_ICH = "ich";

/** Ohne Status-Bedingung zeigt der Feed nur diese; erledigte Vorgänge verdrängen sonst die offenen. */
export const OFFENE_STATUS_FILTER = "neu,geplant,in_arbeit,wartet_kunde";

export const SORTIERUNGEN = [
  { wert: "last_activity_at", label: "Letzte Aktivität" },
  { wert: "prioritaet", label: "Priorität" },
] as const;

function alsListe(w: FilterWert | undefined): string[] {
  if (Array.isArray(w)) return w;
  return typeof w === "string" && w !== "" ? [w] : [];
}

function verschiebeTag(iso: string, delta: number): string {
  const [j, m, t] = iso.split("-").map(Number);
  return isoDatum(new Date(j, m - 1, t + delta));
}

/** `bis` ist beim Backend inklusive, daher "vor X" = bis X-1 und "nach X" = von X+1. */
function faelligBereich(b: FilterBedingung): { von?: string; bis?: string } {
  const w = b.wert;
  const einzel = typeof w === "string" && w ? w : undefined;
  switch (b.op) {
    case "vor":
      return einzel ? { bis: verschiebeTag(einzel, -1) } : {};
    case "nach":
      return einzel ? { von: verschiebeTag(einzel, 1) } : {};
    case "am":
      return einzel ? { von: einzel, bis: einzel } : {};
    case "zwischen":
      return w && typeof w === "object" && !Array.isArray(w) && !("relativ" in w)
        ? { von: w.von || undefined, bis: w.bis || undefined }
        : {};
    case "relativ":
      return w && typeof w === "object" && !Array.isArray(w) && "relativ" in w ? zeitraumAufloesen(w.relativ) : {};
    default:
      return {};
  }
}

function statusParameter(bedingungen: FilterBedingung[]): Record<string, string> {
  const status = bedingungen.filter((b) => b.feld === "status");
  if (status.length === 0) return {};
  let rest: string[] = [...ALLE_STATUS];
  for (const b of status) {
    const werte = alsListe(b.wert);
    // "ist nicht" wird zur Restmenge, weil das Backend nur "Status in Liste" kann.
    rest = rest.filter((s) => (b.op === "ist_nicht" ? !werte.includes(s) : werte.includes(s)));
  }
  return rest.length > 0 ? { status: rest.join(",") } : {};
}

export function bedingungenZuParameter(bedingungen: FilterBedingung[]): Record<string, string> {
  const einzel = (name: string) => (b: FilterBedingung) => {
    const w = alsListe(b.wert)[0];
    return w ? { [name]: w } : {};
  };
  const params = zuServerParametern(bedingungen, {
    kunde: einzel("kunde_id"),
    anlage: einzel("anlage_id"),
    projekt: einzel("projekt_id"),
    leistungstyp: einzel("leistungstyp"),
    abrechnungsart: einzel("abrechnungsart"),
    tag: (b): Record<string, string> => {
      const t = alsListe(b.wert)[0]?.replace(/^#/, "");
      return t ? { tag: t } : {};
    },
    zugewiesen: (b): Record<string, string> => (alsListe(b.wert).includes(PERSON_ICH) ? { nur_meine: "true" } : {}),
  });
  Object.assign(params, statusParameter(bedingungen));
  // Mehrere Fälligkeits-Bedingungen ergeben den Schnitt, nicht "die letzte gewinnt".
  let von: string | undefined;
  let bis: string | undefined;
  for (const b of bedingungen) {
    if (b.feld !== "faellig") continue;
    const r = faelligBereich(b);
    if (r.von && (!von || r.von > von)) von = r.von;
    if (r.bis && (!bis || r.bis < bis)) bis = r.bis;
  }
  if (von) params.faellig_von = von;
  if (bis) params.faellig_bis = bis;
  return params;
}

/** Alte flache Query-Parameter bzw. Filtervorlagen (`filter_json` ohne `v: 2`). `sort` wird bewusst ignoriert. */
export const ALTE_SCHLUESSEL = [
  "status",
  "kunde_id",
  "anlage_id",
  "projekt_id",
  "leistungstyp",
  "abrechnungsart",
  "faellig_von",
  "faellig_bis",
  "tag",
  "nur_meine",
] as const;

export function alteVorlageUmrechnen(alt: Record<string, string>): FilterBedingung[] {
  const ergebnis: FilterBedingung[] = [];
  const ist = (feld: string, schluessel: string) => {
    if (alt[schluessel]) ergebnis.push({ feld, op: "ist", wert: [alt[schluessel]] });
  };
  if (alt.status) {
    const werte = alt.status.split(",").filter(Boolean);
    if (werte.length > 0) ergebnis.push({ feld: "status", op: "ist", wert: werte });
  }
  ist("kunde", "kunde_id");
  ist("anlage", "anlage_id");
  ist("projekt", "projekt_id");
  ist("leistungstyp", "leistungstyp");
  ist("abrechnungsart", "abrechnungsart");
  if (alt.faellig_von || alt.faellig_bis) {
    ergebnis.push({ feld: "faellig", op: "zwischen", wert: { von: alt.faellig_von || undefined, bis: alt.faellig_bis || undefined } });
  }
  if (alt.tag) ergebnis.push({ feld: "tag", op: "enthaelt", wert: [alt.tag.replace(/^#/, "")] });
  if (alt.nur_meine === "true") ergebnis.push({ feld: "zugewiesen", op: "ist", wert: [PERSON_ICH] });
  return ergebnis;
}

/** Links aus Navigation und Kacheln auf die Vorgangsliste mit vorbelegten Bedingungen. */
export function vorgaengeLink(pfad: string, bedingungen: FilterBedingung[]): string {
  return bedingungen.length > 0 ? `${pfad}?f=${bedingungenZuUrl(bedingungen)}` : pfad;
}
