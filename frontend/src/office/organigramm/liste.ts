import type { Position, PositionStatus } from "../../types/organigramm";
import { besetzungText, POSITION_STATUS_LABEL } from "./darstellung";

export interface ListenZeile {
  position: Position;
  tiefe: number;
  // Titel der Vorfahren bis zur Wurzel, inkl. der Position selbst
  pfad: string;
}

export type SortSchluessel = "baum" | "titel" | "typ" | "org_einheit" | "account_typ" | "status" | "sollist";
export type SortRichtung = "auf" | "ab";

export interface PositionsFilter {
  suche: string;
  status: PositionStatus | "alle";
  orgEinheitId: string | "alle";
}

export const KEIN_FILTER: PositionsFilter = { suche: "", status: "alle", orgEinheitId: "alle" };

export function filterAktiv(f: PositionsFilter): boolean {
  return f.suche.trim() !== "" || f.status !== "alle" || f.orgEinheitId !== "alle";
}

function kinderNachEltern(positionen: Position[]): { kinder: Map<string, Position[]>; wurzeln: Position[] } {
  const ids = new Set(positionen.map((p) => p.id));
  const kinder = new Map<string, Position[]>();
  const wurzeln: Position[] = [];
  for (const p of positionen) {
    if (p.parent_id !== null && ids.has(p.parent_id)) {
      const liste = kinder.get(p.parent_id) ?? [];
      liste.push(p);
      kinder.set(p.parent_id, liste);
    } else {
      wurzeln.push(p);
    }
  }
  return { kinder, wurzeln };
}

/** Baumreihenfolge (Tiefensuche, Geschwister in Lieferreihenfolge); Stabsstellen nach den Linien-Kindern. */
export function listenZeilen(positionen: Position[]): ListenZeile[] {
  const { kinder, wurzeln } = kinderNachEltern(positionen);
  const zeilen: ListenZeile[] = [];
  const gesehen = new Set<string>();
  function besuche(p: Position, tiefe: number, vorfahren: string[]) {
    if (gesehen.has(p.id)) return;
    gesehen.add(p.id);
    const pfad = [...vorfahren, p.titel];
    zeilen.push({ position: p, tiefe, pfad: pfad.join(" / ") });
    const unter = kinder.get(p.id) ?? [];
    const geordnet = [...unter.filter((c) => c.typ !== "stabsstelle"), ...unter.filter((c) => c.typ === "stabsstelle")];
    for (const c of geordnet) besuche(c, tiefe + 1, pfad);
  }
  for (const w of wurzeln) besuche(w, 0, []);
  return zeilen;
}

function sortWert(z: ListenZeile, schluessel: SortSchluessel): string | number {
  const p = z.position;
  switch (schluessel) {
    case "titel":
      return p.titel.toLocaleLowerCase("de");
    case "typ":
      return p.typ;
    case "org_einheit":
      return (p.org_einheit?.name ?? "").toLocaleLowerCase("de");
    case "account_typ":
      return (p.account_typ?.name ?? "").toLocaleLowerCase("de");
    case "status":
      return p.status ? POSITION_STATUS_LABEL[p.status] : "";
    case "sollist":
      return (p.ist_besetzung ?? 0) - (p.soll_besetzung ?? 0);
    default:
      return 0;
  }
}

export function sortiereZeilen(zeilen: ListenZeile[], schluessel: SortSchluessel, richtung: SortRichtung): ListenZeile[] {
  if (schluessel === "baum") return richtung === "auf" ? zeilen : [...zeilen].reverse();
  const faktor = richtung === "auf" ? 1 : -1;
  return [...zeilen].sort((a, b) => {
    const wa = sortWert(a, schluessel);
    const wb = sortWert(b, schluessel);
    const vergleich = typeof wa === "number" && typeof wb === "number" ? wa - wb : String(wa).localeCompare(String(wb), "de");
    return vergleich * faktor;
  });
}

export function passtZumFilter(p: Position, f: PositionsFilter): boolean {
  if (p.kontext) return false;
  if (f.status !== "alle" && p.status !== f.status) return false;
  if (f.orgEinheitId !== "alle" && p.org_einheit?.id !== f.orgEinheitId) return false;
  const q = f.suche.trim().toLocaleLowerCase("de");
  if (q) {
    const heu = [p.titel, p.org_einheit?.name, p.account_typ?.name, besetzungText(p)].join(" ").toLocaleLowerCase("de");
    if (!heu.includes(q)) return false;
  }
  return true;
}

/**
 * Treffer plus deren Vorfahren (damit der Pfad im Baum erhalten bleibt).
 * Ohne aktiven Filter: alle sichtbar, keine Sonderbehandlung.
 */
export function filtere(positionen: Position[], f: PositionsFilter): { treffer: Set<string>; sichtbar: Set<string> } {
  if (!filterAktiv(f)) {
    const alle = new Set(positionen.map((p) => p.id));
    return { treffer: alle, sichtbar: alle };
  }
  const nachId = new Map(positionen.map((p) => [p.id, p]));
  const treffer = new Set<string>();
  const sichtbar = new Set<string>();
  for (const p of positionen) {
    if (!passtZumFilter(p, f)) continue;
    treffer.add(p.id);
    let aktuell: Position | undefined = p;
    while (aktuell && !sichtbar.has(aktuell.id)) {
      sichtbar.add(aktuell.id);
      aktuell = aktuell.parent_id ? nachId.get(aktuell.parent_id) : undefined;
    }
  }
  return { treffer, sichtbar };
}
