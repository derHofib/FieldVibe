import type { StatusKey } from "../components/apple/status";
import type {
  Abwesenheit,
  AbwesenheitArt,
  AbwesenheitKalenderEintrag,
  AbwesenheitStatus,
  Urlaubskonto,
} from "../types";
import { parseStunden } from "./arbeitszeit";
import { tageDesMonats, type MonatsTag } from "./zeiterfassung";

export const ABWESENHEIT_ART_LABEL: Record<AbwesenheitArt, string> = {
  urlaub: "Urlaub",
  krankheit: "Krankheit",
  freizeitausgleich: "Freizeitausgleich",
};

export const ABWESENHEIT_ARTEN: AbwesenheitArt[] = ["urlaub", "krankheit", "freizeitausgleich"];

export const ABWESENHEIT_STATUS_LABEL: Record<AbwesenheitStatus, string> = {
  offen: "Offen",
  genehmigt: "Genehmigt",
  abgelehnt: "Abgelehnt",
  zurueckgezogen: "Zurückgezogen",
};

// Status laeuft ueber die sechs StatusKey-Token (fieldvibe-design, Checkliste
// Punkt 1): offen = wartet auf Entscheidung (blau), abgelehnt = rot,
// zurueckgezogen = grau.
export function abwesenheitStatusZuToken(status: AbwesenheitStatus): StatusKey {
  switch (status) {
    case "offen":
      return "neu";
    case "genehmigt":
      return "erledigt";
    case "abgelehnt":
      return "fehlt";
    case "zurueckgezogen":
      return "geplant";
  }
}

/** Tage vom Backend ("4.0", "4.5") als deutsche Zahl ohne unnoetige Nachkommastelle. */
export function formatTage(tage: string | number): string {
  const n = parseStunden(tage);
  const text = Number.isInteger(n) ? String(n) : n.toFixed(1).replace(".", ",");
  return text;
}

export function formatTageMitEinheit(tage: string | number): string {
  const n = parseStunden(tage);
  return `${formatTage(tage)} ${n === 1 ? "Tag" : "Tage"}`;
}

function formatDatum(iso: string, mitJahr: boolean): string {
  const [j, m, t] = iso.split("-");
  return mitJahr ? `${t}.${m}.${j}` : `${t}.${m}.`;
}

/** "02.03. – 06.03.2026" bzw. "02.03.2026" bei einem Tag; halbe Tage als Zusatz. */
export function formatZeitraum(
  a: Pick<Abwesenheit, "von" | "bis" | "halber_tag_von" | "halber_tag_bis">,
): string {
  const basis = a.von === a.bis ? formatDatum(a.von, true) : `${formatDatum(a.von, false)} – ${formatDatum(a.bis, true)}`;
  if (a.von === a.bis) return a.halber_tag_von || a.halber_tag_bis ? `${basis} (halber Tag)` : basis;
  const halb: string[] = [];
  if (a.halber_tag_von) halb.push("erster Tag halb");
  if (a.halber_tag_bis) halb.push("letzter Tag halb");
  return halb.length ? `${basis} (${halb.join(", ")})` : basis;
}

export interface KontoHinweis {
  /** verbleibend < 0: mehr Urlaub genommen/beantragt als Anspruch. */
  ueberzogen: boolean;
  text: string | null;
}

export function kontoHinweis(konto: Pick<Urlaubskonto, "verbleibend">): KontoHinweis {
  const rest = parseStunden(konto.verbleibend);
  if (rest < 0) {
    return { ueberzogen: true, text: `Urlaubskonto um ${formatTageMitEinheit(Math.abs(rest))} überzogen` };
  }
  return { ueberzogen: false, text: null };
}

/** Text zum Resturlaub-Verfall; null, wenn kein Resturlaub oder kein Stichtag. */
export function resturlaubHinweis(
  konto: Pick<Urlaubskonto, "resturlaub" | "resturlaub_verfaellt_am" | "resturlaub_verfallen">,
): string | null {
  if (!konto.resturlaub_verfaellt_am || parseStunden(konto.resturlaub) <= 0) return null;
  const datum = formatDatum(konto.resturlaub_verfaellt_am, true);
  const verfallen = parseStunden(konto.resturlaub_verfallen);
  return verfallen > 0
    ? `${formatTageMitEinheit(verfallen)} Resturlaub am ${datum} verfallen`
    : `Resturlaub verfällt am ${datum}`;
}

/** Offene Antraege, die aeltesten Urlaubsbeginne zuerst. */
export function offeneAntraege(liste: Abwesenheit[]): Abwesenheit[] {
  return liste
    .filter((a) => a.status === "offen")
    .sort((a, b) => a.von.localeCompare(b.von) || a.erstellt_am.localeCompare(b.erstellt_am));
}

export interface KalenderZelle {
  art: AbwesenheitArt;
  halb: boolean;
}

export interface KalenderZeile {
  user_id: string;
  user_name: string;
  zellen: Map<string, KalenderZelle>;
  /** Summe der im Monat liegenden Tage laut Zellen (Wochenenden zaehlen nicht). */
  tage: number;
}

const ART_VORRANG: AbwesenheitArt[] = ["krankheit", "urlaub", "freizeitausgleich"];

/** Zeile je Mitarbeiter mit Zelle je Arbeitstag des Monats. Wochenenden bleiben
 * leer, auch wenn ein Antrag sie ueberspannt (das Backend zaehlt sie nicht);
 * Feiertage/freie Tage kennt die Kalenderantwort nicht und werden mitgefuellt.
 * Treffen mehrere Arten auf einen Tag, gilt dieselbe Rangfolge wie im Saldo. */
export function kalenderRaster(
  eintraege: AbwesenheitKalenderEintrag[],
  jahr: number,
  monat0: number,
): { tage: MonatsTag[]; zeilen: KalenderZeile[] } {
  const tage = tageDesMonats(jahr, monat0);
  const zeilen = new Map<string, KalenderZeile>();
  for (const e of eintraege) {
    let zeile = zeilen.get(e.user_id);
    if (!zeile) {
      zeile = { user_id: e.user_id, user_name: e.user_name, zellen: new Map(), tage: 0 };
      zeilen.set(e.user_id, zeile);
    }
    for (const t of tage) {
      if (t.istWochenende || t.tag < e.von || t.tag > e.bis) continue;
      const halb = (t.tag === e.von && e.halber_tag_von) || (t.tag === e.bis && e.halber_tag_bis);
      const vorher = zeile.zellen.get(t.tag);
      if (vorher && ART_VORRANG.indexOf(vorher.art) <= ART_VORRANG.indexOf(e.art)) continue;
      zeile.zellen.set(t.tag, { art: e.art, halb });
    }
  }
  const liste = [...zeilen.values()];
  for (const z of liste) {
    z.tage = [...z.zellen.values()].reduce((s, c) => s + (c.halb ? 0.5 : 1), 0);
  }
  liste.sort((a, b) => a.user_name.localeCompare(b.user_name, "de"));
  return { tage, zeilen: liste };
}
