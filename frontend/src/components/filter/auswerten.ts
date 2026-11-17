import {
  OPERATOR_LABEL,
  OPERATOREN_OHNE_WERT,
  relativLabel,
  type FilterBedingung,
  type FilterFeld,
  type FilterFeldTyp,
  type FilterOption,
  type RelativerZeitraum,
} from "./typen";

/** Beide Seiten (Zeile und Eingabe) laufen durch dieselbe Funktion, damit "ae" ein "ä" findet und umgekehrt. */
export function normalisiere(s: string): string {
  return s
    .toLowerCase()
    .trim()
    .replace(/ß/g, "ss")
    .replace(/ä/g, "ae")
    .replace(/ö/g, "oe")
    .replace(/ü/g, "ue")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");
}

/** Deutsches Format ("1.000,50", auch mit "€"/Leerzeichen); Punkt gilt als Tausendertrenner. */
export function parseDeutscheZahl(s: string): number | null {
  const bereinigt = s.replace(/[€\s]/g, "").replace(/\./g, "").replace(",", ".");
  if (bereinigt === "" || bereinigt === "-") return null;
  const n = Number(bereinigt);
  return Number.isFinite(n) ? n : null;
}

const pad = (n: number) => String(n).padStart(2, "0");

export function isoDatum(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Tagesgenauer ISO-Schlüssel in lokaler Zeit; reine Datumsstrings bleiben unverändert (keine Zeitzonen-Verschiebung). */
function tagSchluessel(v: unknown): string | null {
  if (v == null || v === "") return null;
  const s = String(v);
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : isoDatum(d);
}

export function zeitraumAufloesen(relativ: RelativerZeitraum, heute: Date = new Date()): { von?: string; bis?: string } {
  const y = heute.getFullYear();
  const m = heute.getMonth();
  const t = heute.getDate();
  const tag = (delta: number) => isoDatum(new Date(y, m, t + delta));
  switch (relativ) {
    case "ueberfaellig":
      return { bis: tag(-1) };
    case "heute":
      return { von: tag(0), bis: tag(0) };
    case "woche": {
      const abMontag = (heute.getDay() + 6) % 7;
      return { von: tag(-abMontag), bis: tag(-abMontag + 6) };
    }
    case "naechste_7":
      return { von: tag(0), bis: tag(6) };
    case "monat":
      return { von: isoDatum(new Date(y, m, 1)), bis: isoDatum(new Date(y, m + 1, 0)) };
    default: {
      const n = Number(relativ.slice("letzte_".length));
      return Number.isFinite(n) && n > 0 ? { von: tag(-n + 1), bis: tag(0) } : {};
    }
  }
}

type ZeilenWert = string | number | boolean | string[] | null | undefined;

function istLeer(w: ZeilenWert): boolean {
  return w == null || w === "" || (Array.isArray(w) && w.length === 0);
}

function alsListe(w: unknown): string[] {
  if (Array.isArray(w)) return w.map(String);
  if (w == null || w === "") return [];
  return [String(w)];
}

function alsBereich(w: unknown): { von?: string; bis?: string } {
  return w && typeof w === "object" && !Array.isArray(w) ? (w as { von?: string; bis?: string }) : {};
}

export function bedingungErfuellt(
  wert: ZeilenWert,
  bedingung: FilterBedingung,
  typ: FilterFeldTyp,
  heute: Date = new Date(),
): boolean {
  const { op } = bedingung;
  if (op === "leer") return istLeer(wert);
  if (op === "nicht_leer") return !istLeer(wert);
  const bw = bedingung.wert;

  switch (typ) {
    case "text": {
      if (typeof bw !== "string" || bw.trim() === "") return true;
      const z = normalisiere(String(wert ?? ""));
      const w = normalisiere(bw);
      if (op === "enthaelt") return z.includes(w);
      if (op === "enthaelt_nicht") return !z.includes(w);
      if (op === "ist") return z === w;
      if (op === "ist_nicht") return z !== w;
      if (op === "beginnt_mit") return z.startsWith(w);
      if (op === "endet_mit") return z.endsWith(w);
      return true;
    }
    case "auswahl":
    case "verknuepfung":
    case "person": {
      const gesucht = alsListe(bw);
      if (gesucht.length === 0) return true;
      const treffer = alsListe(wert).some((z) => gesucht.includes(z));
      return op === "ist_nicht" ? !treffer : treffer;
    }
    case "liste": {
      const gesucht = alsListe(bw);
      if (gesucht.length === 0) return true;
      const treffer = alsListe(wert).some((z) => gesucht.includes(z));
      return op === "enthaelt_nicht" ? !treffer : treffer;
    }
    case "janein":
      return Boolean(wert) === (bw === "ja");
    case "zahl":
    case "betrag": {
      const n = typeof wert === "number" ? wert : typeof wert === "string" ? parseDeutscheZahl(wert) : null;
      if (n === null) return false;
      if (op === "zwischen") {
        const { von, bis } = alsBereich(bw);
        const v = von ? parseDeutscheZahl(von) : null;
        const b = bis ? parseDeutscheZahl(bis) : null;
        return (v === null || n >= v) && (b === null || n <= b);
      }
      const ref = typeof bw === "string" ? parseDeutscheZahl(bw) : null;
      if (ref === null) return true;
      if (op === "gleich") return n === ref;
      if (op === "ungleich") return n !== ref;
      if (op === "gt") return n > ref;
      if (op === "gte") return n >= ref;
      if (op === "lt") return n < ref;
      if (op === "lte") return n <= ref;
      return true;
    }
    case "datum": {
      const d = tagSchluessel(wert);
      if (d === null) return false;
      if (op === "relativ") {
        const rel = bw && typeof bw === "object" && "relativ" in bw ? bw.relativ : null;
        if (!rel) return true;
        const { von, bis } = zeitraumAufloesen(rel, heute);
        return (!von || d >= von) && (!bis || d <= bis);
      }
      if (op === "zwischen") {
        const { von, bis } = alsBereich(bw);
        return (!von || d >= von) && (!bis || d <= bis);
      }
      const ref = typeof bw === "string" ? tagSchluessel(bw) : null;
      if (ref === null) return true;
      if (op === "am") return d === ref;
      if (op === "vor") return d < ref;
      if (op === "nach") return d > ref;
      return true;
    }
  }
}

export function filterAnwenden<T>(zeilen: T[], bedingungen: FilterBedingung[], felder: FilterFeld<T>[]): T[] {
  const nachKey = new Map(felder.map((f) => [f.key, f]));
  const aktiv = bedingungen.flatMap((b) => {
    const feld = nachKey.get(b.feld);
    return feld?.wert ? [{ b, feld }] : [];
  });
  if (aktiv.length === 0) return zeilen;
  const heute = new Date();
  return zeilen.filter((z) => aktiv.every(({ b, feld }) => bedingungErfuellt(feld.wert!(z), b, feld.typ, heute)));
}

export function sucheAnwenden<T>(zeilen: T[], suche: string, suchtext: (z: T) => string): T[] {
  const woerter = normalisiere(suche).split(/\s+/).filter(Boolean);
  if (woerter.length === 0) return zeilen;
  return zeilen.filter((z) => {
    const text = normalisiere(suchtext(z));
    return woerter.every((w) => text.includes(w));
  });
}

export function formatDatum(iso: string, kurz = false): string {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return kurz ? `${d}.${m}.` : `${d}.${m}.${y}`;
}

const BETRAG_FORMAT = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const ZAHL_FORMAT = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 });

function formatZahl(s: string, betrag: boolean): string {
  const n = parseDeutscheZahl(s);
  if (n === null) return s;
  return betrag ? `${BETRAG_FORMAT.format(n)} €` : ZAHL_FORMAT.format(n);
}

export function pillenTeile<T>(b: FilterBedingung, feld: FilterFeld<T>): { spalte: string; operator: string; wert: string } {
  const spalte = feld.label;
  const operator = OPERATOR_LABEL[b.op];
  if (OPERATOREN_OHNE_WERT.includes(b.op)) return { spalte, operator, wert: "" };
  const w = b.wert;
  let wert = "";

  if (b.op === "relativ" && w && typeof w === "object" && "relativ" in w) {
    wert = relativLabel(w.relativ);
  } else if (b.op === "zwischen") {
    const { von, bis } = alsBereich(w);
    if (feld.typ === "datum") {
      const gleichesJahr = von && bis && von.slice(0, 4) === bis.slice(0, 4);
      wert = `${von ? formatDatum(von, !!gleichesJahr) : ""} – ${bis ? formatDatum(bis) : ""}`;
    } else {
      const betrag = feld.typ === "betrag";
      wert = `${von ? formatZahl(von, betrag) : ""} – ${bis ? formatZahl(bis, betrag) : ""}`;
    }
  } else if (typeof w === "string") {
    if (feld.typ === "datum") wert = formatDatum(w);
    else if (feld.typ === "zahl" || feld.typ === "betrag") wert = formatZahl(w, feld.typ === "betrag");
    else if (feld.typ === "auswahl" || feld.typ === "verknuepfung" || feld.typ === "person" || feld.typ === "liste")
      wert = feld.optionen?.find((o) => o.wert === w)?.label ?? w;
    else wert = w;
  } else if (Array.isArray(w)) {
    wert = w.map((v) => feld.optionen?.find((o) => o.wert === v)?.label ?? v).join(", ");
  }
  return { spalte, operator, wert };
}

export function zuServerParametern(
  bedingungen: FilterBedingung[],
  abbildung: Record<string, (b: FilterBedingung) => Record<string, string>>,
): Record<string, string> {
  const ergebnis: Record<string, string> = {};
  for (const b of bedingungen) Object.assign(ergebnis, abbildung[b.feld]?.(b));
  return ergebnis;
}

/** Für Backends, die nur "Status in Liste" können: "ist nicht" wird zur Restmenge. */
export function auswahlKomplement(gewaehlt: string[], alleOptionen: (FilterOption | string)[]): string[] {
  return alleOptionen.map((o) => (typeof o === "string" ? o : o.wert)).filter((w) => !gewaehlt.includes(w));
}

function kanonisch(b: FilterBedingung): string {
  const w = b.wert;
  const norm = Array.isArray(w) ? [...w].sort() : w;
  return JSON.stringify([b.feld, b.op, norm ?? null]);
}

/** Gleichheit ohne Rücksicht auf die Reihenfolge der Bedingungen (und der Werte innerhalb einer Pille). */
export function bedingungenGleich(a: FilterBedingung[], b: FilterBedingung[]): boolean {
  if (a.length !== b.length) return false;
  const x = a.map(kanonisch).sort();
  const y = b.map(kanonisch).sort();
  return x.every((v, i) => v === y[i]);
}
