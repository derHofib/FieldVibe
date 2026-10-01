import type { ZeitplanAbhaengigkeit, ZeitplanAbhaengigkeitArt, ZeitplanElement, ZeitplanTermin, ZeitplanTyp, ZeitplanVerschiebeModus } from "../../../types";

// Reine Logik des Gantt-Zeitplans. Alles wird in KALENDERTAGEN gerechnet:
// ein Datum "YYYY-MM-DD" ist hier eine ganze Zahl (Tage seit 1970-01-01,
// UTC). Date-Objekte in Lokalzeit oder toISOString() waeren eine
// Zeitzonen-/Sommerzeitfalle (Tag springt um 1, siehe toDateInput() in
// utils/zeiterfassung.ts) -- darum rechnet dieses Modul nur ueber
// Date.UTC und die getUTC*-Zugriffe.

export const ZEILEN_HOEHE = 36;
export const BALKEN_HOEHE = 22;
export const PHASEN_HOEHE = 10;
export const RAUTE_GROESSE = 16;

export type Zoom = "tag" | "woche" | "monat";
export const PX_PRO_TAG: Record<Zoom, number> = { tag: 32, woche: 14, monat: 4 };

const MS_PRO_TAG = 86_400_000;
const MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"];
const MONATE_KURZ = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];

// --- Datumsmathe ----------------------------------------------------------

export function parseTag(s: string): number {
  const [j, m, t] = s.split("-").map(Number);
  return Math.round(Date.UTC(j, m - 1, t) / MS_PRO_TAG);
}

export function formatTag(tag: number): string {
  const d = new Date(tag * MS_PRO_TAG);
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
}

export function addTage(s: string, n: number): string {
  return formatTag(parseTag(s) + n);
}

/** Anzahl Tage von a nach b (b - a), beide "YYYY-MM-DD". */
export function diffTage(a: string, b: string): number {
  return parseTag(b) - parseTag(a);
}

/** Heutiger Kalendertag aus der LOKALEN Uhr des Browsers (nicht UTC: um
 * 00:30 deutscher Zeit ist es in UTC noch gestern). */
export function heuteTag(jetzt: Date = new Date()): number {
  return Math.round(Date.UTC(jetzt.getFullYear(), jetzt.getMonth(), jetzt.getDate()) / MS_PRO_TAG);
}

export function ymd(tag: number): { jahr: number; monat: number; tag: number } {
  const d = new Date(tag * MS_PRO_TAG);
  return { jahr: d.getUTCFullYear(), monat: d.getUTCMonth() + 1, tag: d.getUTCDate() };
}

/** 0 = Montag ... 6 = Sonntag. 1970-01-01 war ein Donnerstag. */
export function wochentag(tag: number): number {
  return (((tag + 3) % 7) + 7) % 7;
}

export function istWochenende(tag: number): boolean {
  return wochentag(tag) >= 5;
}

export function montagVon(tag: number): number {
  return tag - wochentag(tag);
}

/** ISO-8601-Kalenderwoche (Woche mit dem Donnerstag im Jahr). */
export function isoKw(tag: number): number {
  const donnerstag = montagVon(tag) + 3;
  const jahr = ymd(donnerstag).jahr;
  const jan1 = Math.round(Date.UTC(jahr, 0, 1) / MS_PRO_TAG);
  return Math.floor((donnerstag - jan1) / 7) + 1;
}

export function formatKurz(tag: number): string {
  const { monat, tag: t } = ymd(tag);
  return `${String(t).padStart(2, "0")}.${String(monat).padStart(2, "0")}.`;
}

/** Dauer in Kalendertagen, Ende inklusiv. */
export function dauerTage(start: string, ende: string): number {
  return diffTage(start, ende) + 1;
}

/** Tooltip-/Infozeile beim Ziehen: "12.10. – 15.10. (4 Tage)". */
export function formatBereich(start: string, ende: string): string {
  const n = dauerTage(start, ende);
  return `${formatKurz(parseTag(start))} – ${formatKurz(parseTag(ende))} (${n} ${n === 1 ? "Tag" : "Tage"})`;
}

// --- Pixel <-> Datum ------------------------------------------------------

export function tagZuX(tag: number, ursprung: number, zoom: Zoom): number {
  return (tag - ursprung) * PX_PRO_TAG[zoom];
}

export function xZuTag(x: number, ursprung: number, zoom: Zoom): number {
  return ursprung + Math.floor(x / PX_PRO_TAG[zoom]);
}

/** Pixel-Verschiebung -> ganze Tage (Tagesraster). */
export function pixelZuTagen(dx: number, zoom: Zoom): number {
  const n = Math.round(dx / PX_PRO_TAG[zoom]);
  return n === 0 ? 0 : n; // verhindert -0
}

export interface Zeitbereich {
  ursprung: number;
  anzahlTage: number;
}

/** Sichtbarer Bereich: alle datierten Elemente plus Puffer, an Wochen
 * ausgerichtet, mindestens minTage (der Aufrufer waehlt es je Zoom, damit ein
 * leerer/kurzer Plan die Flaeche fuellt). */
export function zeitbereich(elemente: ZeitplanElement[], heute: number, minTage = 63): Zeitbereich {
  let min = heute;
  let max = heute;
  for (const e of elemente) {
    if (e.start_am) min = Math.min(min, parseTag(e.start_am));
    if (e.ende_am) max = Math.max(max, parseTag(e.ende_am));
    else if (e.start_am) max = Math.max(max, parseTag(e.start_am));
    for (const t of e.termine ?? []) {
      const tag = terminTag(t);
      min = Math.min(min, tag);
      max = Math.max(max, tag);
    }
  }
  const ursprung = montagVon(min - 7);
  let ende = montagVon(max + 21) + 7;
  ende = Math.max(ende, ursprung + minTage);
  return { ursprung, anzahlTage: ende - ursprung };
}

export interface KopfSegment {
  label: string;
  von: number;
  bis: number; // exklusiv
}

/** Zweizeiliger Zeitleisten-Kopf je Zoom: Tag = Monat / Tag, Woche =
 * Monat / KW, Monat = Jahr / Monat. */
export function kopfSegmente(ursprung: number, anzahlTage: number, zoom: Zoom): { oben: KopfSegment[]; unten: KopfSegment[] } {
  const ende = ursprung + anzahlTage;
  const oben: KopfSegment[] = [];
  const unten: KopfSegment[] = [];

  const gruppiere = (schluessel: (t: number) => string, label: (t: number) => string, ziel: KopfSegment[]) => {
    let start = ursprung;
    for (let t = ursprung + 1; t <= ende; t++) {
      if (t === ende || schluessel(t) !== schluessel(start)) {
        ziel.push({ label: label(start), von: start, bis: t });
        start = t;
      }
    }
  };

  const monatKey = (t: number) => `${ymd(t).jahr}-${ymd(t).monat}`;
  const monatLabel = (t: number) => `${MONATE[ymd(t).monat - 1]} ${ymd(t).jahr}`;

  if (zoom === "tag") {
    gruppiere(monatKey, monatLabel, oben);
    for (let t = ursprung; t < ende; t++) unten.push({ label: String(ymd(t).tag), von: t, bis: t + 1 });
  } else if (zoom === "woche") {
    gruppiere(monatKey, monatLabel, oben);
    gruppiere((t) => String(montagVon(t)), (t) => `KW ${isoKw(t)}`, unten);
  } else {
    gruppiere((t) => String(ymd(t).jahr), (t) => String(ymd(t).jahr), oben);
    gruppiere(monatKey, (t) => MONATE_KURZ[ymd(t).monat - 1], unten);
  }
  return { oben, unten };
}

// --- Positionen / Spannen ---------------------------------------------------

export interface Zeitraum {
  start: number;
  ende: number; // inklusiv; beim Meilenstein == start
}

export interface Aenderung {
  start_am: string;
  ende_am: string;
}

/** Eigener Zeitraum eines Elements (null ohne Startdatum). Meilenstein:
 * ende == start. Ein fehlendes Ende bei Schritten gilt als 1 Tag. */
export function elementZeitraum(e: ZeitplanElement): Zeitraum | null {
  if (!e.start_am) return null;
  const start = parseTag(e.start_am);
  if (e.typ === "meilenstein") return { start, ende: start };
  return { start, ende: Math.max(start, e.ende_am ? parseTag(e.ende_am) : start) };
}

/** Zeitraeume aller Elemente fuer die Darstellung: Schritte/Meilensteine
 * aus den Daten (vorschau ueberschreibt), Phasen als Spanne (min/max) ihrer
 * datierten Kinder -- erst ohne datierte Kinder zaehlt das eigene Datum. */
export function anzeigeZeitraeume(elemente: ZeitplanElement[], vorschau?: Map<string, Aenderung>): Map<string, Zeitraum> {
  const pos = new Map<string, Zeitraum>();
  for (const e of elemente) {
    if (e.typ === "phase") continue;
    const v = vorschau?.get(e.id);
    if (v) pos.set(e.id, { start: parseTag(v.start_am), ende: e.typ === "meilenstein" ? parseTag(v.start_am) : parseTag(v.ende_am) });
    else {
      const z = elementZeitraum(e);
      if (z) pos.set(e.id, z);
    }
  }
  for (const e of elemente) {
    if (e.typ !== "phase") continue;
    let min = Infinity;
    let max = -Infinity;
    for (const k of elemente) {
      if (k.phase_id !== e.id || k.typ === "phase") continue;
      const z = pos.get(k.id);
      if (!z) continue;
      min = Math.min(min, z.start);
      max = Math.max(max, z.ende);
    }
    if (min !== Infinity) pos.set(e.id, { start: min, ende: max });
    else {
      const z = elementZeitraum(e);
      if (z) pos.set(e.id, z);
    }
  }
  return pos;
}

export type ZiehArt = "verschieben" | "dauer";

/** Neue Daten eines einzelnen Schritts/Meilensteins nach Ziehen um delta
 * Tage. Dauer: mindestens 1 Tag; Meilensteine haben keine Dauer. */
export function elementAenderung(e: ZeitplanElement, art: ZiehArt, delta: number): Aenderung | null {
  const z = elementZeitraum(e);
  if (!z || e.typ === "phase") return null;
  if (e.typ === "meilenstein") {
    if (art === "dauer") return null;
    return { start_am: formatTag(z.start + delta), ende_am: formatTag(z.start + delta) };
  }
  if (art === "verschieben") return { start_am: formatTag(z.start + delta), ende_am: formatTag(z.ende + delta) };
  return { start_am: formatTag(z.start), ende_am: formatTag(Math.max(z.start, z.ende + delta)) };
}

/** Phase verschieben = alle datierten, nicht gesperrten Kinder um dasselbe Delta. */
export function phaseVerschieben(elemente: ZeitplanElement[], phaseId: string, delta: number): Map<string, Aenderung> {
  const out = new Map<string, Aenderung>();
  for (const e of elemente) {
    // Gesperrte Meilensteine (Datum aus Bestellung) bleiben stehen -- wie im Backend.
    if (e.phase_id !== phaseId || e.typ === "phase" || e.datum_gesperrt) continue;
    const a = elementAenderung(e, "verschieben", delta);
    if (a) out.set(e.id, a);
  }
  return out;
}

// --- Abhaengigkeiten: Vorschau-Propagation ------------------------------------

/** Frueheste Startposition des Nachfolgers laut einer Verbindung. Bei
 * Ende -> Ende bestimmt das Ende die Grenze, der Start folgt aus der Dauer. */
function fruehesterStart(
  vorgaenger: Zeitraum,
  vorgaengerTyp: ZeitplanTyp,
  art: ZeitplanAbhaengigkeitArt,
  versatz: number,
  dauerNachfolger: number,
): number {
  if (art === "anfang_anfang") return vorgaenger.start + versatz;
  if (art === "ende_ende") return vorgaenger.ende + versatz - dauerNachfolger;
  return vorgaengerTyp === "meilenstein" ? vorgaenger.start + versatz : vorgaenger.ende + 1 + versatz;
}

/** Bezugspunkt des Vorgaengers fuer den Modus "immer": Start bei
 * Anfang -> Anfang, sonst Ende. */
function bezugspunkt(z: Zeitraum, art: ZeitplanAbhaengigkeitArt): number {
  return art === "anfang_anfang" ? z.start : z.ende;
}

/** Live-Vorschau beim Ziehen -- spiegelt die Fachregeln des Backends (das
 * bleibt maßgeblich). Liefert alle geaenderten Schritte/Meilensteine
 * (inkl. der direkt gezogenen).
 *  - bei_konflikt: Nachfolger nur nach hinten schieben, wenn er sonst vor
 *    dem fruehesten Start laege (Dauer bleibt).
 *  - immer: Nachfolger um dasselbe Delta wie das Ende des Vorgaengers
 *    (bei Anfang -> Anfang: dessen Start; auch nach vorne), danach Konfliktregel.
 *  - datum_gesperrt-Elemente bleiben fix (auch als Nachfolger).
 *  - Mehrere Vorgaenger: Maximum der fruehesten Starts; im Modus "immer"
 *    das groesste Delta der bewegten Vorgaenger. */
export function berechneVorschau(
  elemente: ZeitplanElement[],
  abhaengigkeiten: ZeitplanAbhaengigkeit[],
  modus: ZeitplanVerschiebeModus,
  direkt: Map<string, Aenderung>,
): Map<string, Aenderung> {
  const typ = new Map(elemente.map((e) => [e.id, e.typ]));
  const alt = new Map<string, Zeitraum>();
  for (const e of elemente) {
    if (e.typ === "phase") continue;
    const z = elementZeitraum(e);
    if (z) alt.set(e.id, z);
  }
  const pos = new Map(alt);
  const fix = new Set<string>();
  // Gesperrte Elemente werden nie verschoben, ihre Nachfolger aber weiter gegen sie geprueft.
  const gesperrt = new Set(elemente.filter((e) => e.datum_gesperrt).map((e) => e.id));
  for (const [id, a] of direkt) {
    if (typ.get(id) === undefined || typ.get(id) === "phase") continue;
    pos.set(id, { start: parseTag(a.start_am), ende: typ.get(id) === "meilenstein" ? parseTag(a.start_am) : parseTag(a.ende_am) });
    fix.add(id);
  }

  const nachfolger = new Map<string, ZeitplanAbhaengigkeit[]>();
  const vorgaenger = new Map<string, ZeitplanAbhaengigkeit[]>();
  for (const d of abhaengigkeiten) {
    if (!pos.has(d.vorgaenger_id) || !pos.has(d.nachfolger_id)) continue;
    nachfolger.set(d.vorgaenger_id, [...(nachfolger.get(d.vorgaenger_id) ?? []), d]);
    vorgaenger.set(d.nachfolger_id, [...(vorgaenger.get(d.nachfolger_id) ?? []), d]);
  }

  // Betroffene Knoten (alles, was von einem gezogenen Element aus erreichbar ist).
  const betroffen = new Set<string>(fix);
  const stapel = [...fix];
  while (stapel.length) {
    const n = stapel.pop()!;
    for (const d of nachfolger.get(n) ?? []) {
      if (!betroffen.has(d.nachfolger_id)) {
        betroffen.add(d.nachfolger_id);
        stapel.push(d.nachfolger_id);
      }
    }
  }

  // Kahn auf dem betroffenen Teilgraphen: ein Nachfolger wird erst
  // gerechnet, wenn alle seine betroffenen Vorgaenger fertig sind (Diamant!).
  const eingang = new Map<string, number>();
  for (const id of betroffen) {
    eingang.set(id, (vorgaenger.get(id) ?? []).filter((d) => betroffen.has(d.vorgaenger_id)).length);
  }
  const bereit = [...betroffen].filter((id) => eingang.get(id) === 0);
  while (bereit.length) {
    const n = bereit.shift()!;
    if (!fix.has(n) && !gesperrt.has(n)) {
      const eigen = pos.get(n)!;
      const dauer = eigen.ende - eigen.start;
      let start = eigen.start;
      if (modus === "immer") {
        let delta: number | null = null;
        for (const d of vorgaenger.get(n) ?? []) {
          const neu = pos.get(d.vorgaenger_id)!;
          const vorher = alt.get(d.vorgaenger_id)!;
          const dd = bezugspunkt(neu, d.art) - bezugspunkt(vorher, d.art);
          if (dd !== 0) delta = delta === null ? dd : Math.max(delta, dd);
        }
        if (delta !== null) start += delta;
      }
      for (const d of vorgaenger.get(n) ?? []) {
        const frueh = fruehesterStart(pos.get(d.vorgaenger_id)!, typ.get(d.vorgaenger_id)!, d.art ?? "ende_anfang", d.versatz_tage, dauer);
        if (start < frueh) start = frueh;
      }
      pos.set(n, { start, ende: start + dauer });
    }
    for (const d of nachfolger.get(n) ?? []) {
      const rest = (eingang.get(d.nachfolger_id) ?? 0) - 1;
      eingang.set(d.nachfolger_id, rest);
      if (rest === 0) bereit.push(d.nachfolger_id);
    }
  }

  const out = new Map<string, Aenderung>();
  for (const [id, z] of pos) {
    const a = alt.get(id);
    if (fix.has(id) || !a || a.start !== z.start || a.ende !== z.ende) {
      out.set(id, { start_am: formatTag(z.start), ende_am: formatTag(z.ende) });
    }
  }
  return out;
}

// --- Zyklus-Erkennung / Verbindungsziele ---------------------------------------

/** Wuerde vorgaenger -> nachfolger einen Kreis erzeugen? (Selbstverbindung
 * zaehlt auch.) Sofortiges Feedback; das Backend prueft ebenfalls (409). */
export function wuerdeKreisErzeugen(abhaengigkeiten: ZeitplanAbhaengigkeit[], vorgaengerId: string, nachfolgerId: string): boolean {
  if (vorgaengerId === nachfolgerId) return true;
  const gesehen = new Set<string>();
  const stapel = [nachfolgerId];
  while (stapel.length) {
    const n = stapel.pop()!;
    if (n === vorgaengerId) return true;
    if (gesehen.has(n)) continue;
    gesehen.add(n);
    for (const d of abhaengigkeiten) if (d.vorgaenger_id === n) stapel.push(d.nachfolger_id);
  }
  return false;
}

/** Nur Schritte/Meilensteine mit Datum, nicht dasselbe Element, noch keine
 * gleiche Verbindung, kein Kreis. */
export function istGueltigesVerbindungsziel(
  elemente: ZeitplanElement[],
  abhaengigkeiten: ZeitplanAbhaengigkeit[],
  quelleId: string,
  zielId: string,
): boolean {
  if (quelleId === zielId) return false;
  const q = elemente.find((e) => e.id === quelleId);
  const z = elemente.find((e) => e.id === zielId);
  if (!q || !z) return false;
  if (q.typ === "phase" || z.typ === "phase" || !q.start_am || !z.start_am) return false;
  if (abhaengigkeiten.some((d) => d.vorgaenger_id === quelleId && d.nachfolger_id === zielId)) return false;
  return !wuerdeKreisErzeugen(abhaengigkeiten, quelleId, zielId);
}

// --- Geometrie ---------------------------------------------------------------------

export interface BalkenRechteck {
  x: number;
  y: number;
  w: number;
  h: number;
  cy: number;
  /** x-Koordinaten fuer Verbindungslinien (Meilenstein: Raute-Spitzen). */
  links: number;
  rechts: number;
}

export function balkenRechteck(typ: ZeitplanTyp, z: Zeitraum, zeile: number, zoom: Zoom, ursprung: number): BalkenRechteck {
  const px = PX_PRO_TAG[zoom];
  const zeileY = zeile * ZEILEN_HOEHE;
  const cy = zeileY + ZEILEN_HOEHE / 2;
  const x = tagZuX(z.start, ursprung, zoom);
  if (typ === "meilenstein") {
    const cx = x + px / 2;
    return { x: cx - RAUTE_GROESSE / 2, y: cy - RAUTE_GROESSE / 2, w: RAUTE_GROESSE, h: RAUTE_GROESSE, cy, links: cx - RAUTE_GROESSE / 2, rechts: cx + RAUTE_GROESSE / 2 };
  }
  const w = Math.max(px, (z.ende - z.start + 1) * px);
  const h = typ === "phase" ? PHASEN_HOEHE : BALKEN_HOEHE;
  return { x, y: cy - h / 2, w, h, cy, links: x, rechts: x + w };
}

export interface Punkt {
  x: number;
  y: number;
}

/** Eckpunkte der Verbindungslinie Vorgaenger-Ende -> Nachfolger-Anfang.
 * Normal: rechts, senkrecht, rechts in den Nachfolger. Liegt der
 * Nachfolger-Anfang nicht mindestens zwei Abstaende hinter dem Ende des
 * Vorgaengers, Umweg ueber die Zeilengrenze (nach unten bzw. -- bei
 * Nachfolger oberhalb -- nach oben) und von links in den Nachfolger. */
export function verbindungsPunkte(von: Punkt, nach: Punkt, zeilenHoehe = ZEILEN_HOEHE, abstand = 8): Punkt[] {
  if (nach.x - von.x >= 2 * abstand) {
    const xm = von.x + abstand;
    return [von, { x: xm, y: von.y }, { x: xm, y: nach.y }, nach];
  }
  const yUm = von.y + (nach.y >= von.y ? 1 : -1) * (zeilenHoehe / 2);
  return [
    von,
    { x: von.x + abstand, y: von.y },
    { x: von.x + abstand, y: yUm },
    { x: nach.x - abstand, y: yUm },
    { x: nach.x - abstand, y: nach.y },
    nach,
  ];
}

/** Anfang -> Anfang: beide Linienenden liegen links an den Balken, die Linie
 * laeuft links herum (einen Abstand links vom linkeren Balkenanfang) und
 * kommt von links in den Nachfolger -- Pfeil zeigt nach rechts. */
export function verbindungsPunkteAnfangAnfang(von: Punkt, nach: Punkt, abstand = 8): Punkt[] {
  const xm = Math.min(von.x, nach.x) - abstand;
  return [von, { x: xm, y: von.y }, { x: xm, y: nach.y }, nach];
}

/** Ende -> Ende: beide Enden liegen rechts, die Linie laeuft rechts herum
 * und kommt von rechts in den Nachfolger -- Pfeil zeigt nach links. */
export function verbindungsPunkteEndeEnde(von: Punkt, nach: Punkt, abstand = 8): Punkt[] {
  const xm = Math.max(von.x, nach.x) + abstand;
  return [von, { x: xm, y: von.y }, { x: xm, y: nach.y }, nach];
}

/** Anschlusspunkte einer Verbindung je Art: Ende/Anfang des Vorgaengers
 * (EA, EE: rechts; AA: links) und Ziel am Nachfolger (EE: rechts, sonst links). */
export function verbindungsAnker(art: ZeitplanAbhaengigkeitArt, v: BalkenRechteck, n: BalkenRechteck): { von: Punkt; nach: Punkt } {
  return {
    von: { x: art === "anfang_anfang" ? v.links : v.rechts, y: v.cy },
    nach: { x: art === "ende_ende" ? n.rechts : n.links, y: n.cy },
  };
}

/** Pfeilspitze am Ziel: bei Ende -> Ende von rechts kommend (zeigt nach links). */
export function pfeilZeigtNachLinks(art: ZeitplanAbhaengigkeitArt): boolean {
  return art === "ende_ende";
}

/** Polylinie mit kleinen Quadratik-Rundungen an den Ecken als SVG-Pfad. */
export function rundePfad(punkte: Punkt[], radius = 5): string {
  const p = punkte.filter((q, i) => i === 0 || q.x !== punkte[i - 1].x || q.y !== punkte[i - 1].y);
  if (p.length === 0) return "";
  const f = (n: number) => String(Math.round(n * 100) / 100);
  let d = `M ${f(p[0].x)} ${f(p[0].y)}`;
  for (let i = 1; i < p.length - 1; i++) {
    const a = p[i - 1];
    const b = p[i];
    const c = p[i + 1];
    const l1 = Math.hypot(b.x - a.x, b.y - a.y);
    const l2 = Math.hypot(c.x - b.x, c.y - b.y);
    const r = Math.min(radius, l1 / 2, l2 / 2);
    const vor = { x: b.x - ((b.x - a.x) / l1) * r, y: b.y - ((b.y - a.y) / l1) * r };
    const nach = { x: b.x + ((c.x - b.x) / l2) * r, y: b.y + ((c.y - b.y) / l2) * r };
    d += ` L ${f(vor.x)} ${f(vor.y)} Q ${f(b.x)} ${f(b.y)} ${f(nach.x)} ${f(nach.y)}`;
  }
  if (p.length > 1) d += ` L ${f(p[p.length - 1].x)} ${f(p[p.length - 1].y)}`;
  return d;
}

export function verbindungsPfad(von: Punkt, nach: Punkt, art: ZeitplanAbhaengigkeitArt = "ende_anfang"): string {
  if (art === "anfang_anfang") return rundePfad(verbindungsPunkteAnfangAnfang(von, nach));
  if (art === "ende_ende") return rundePfad(verbindungsPunkteEndeEnde(von, nach));
  return rundePfad(verbindungsPunkte(von, nach));
}

// --- Verbindungsarten / Ziehen -------------------------------------------------------

export const ART_LABEL: Record<ZeitplanAbhaengigkeitArt, string> = {
  ende_anfang: "Ende → Anfang",
  anfang_anfang: "Anfang → Anfang",
  ende_ende: "Ende → Ende",
};

export const ART_ERKLAERUNG: Record<ZeitplanAbhaengigkeitArt, string> = {
  ende_anfang: "Nachfolger startet nach dem Ende des Vorgängers",
  anfang_anfang: "Nachfolger startet frühestens mit dem Vorgänger",
  ende_ende: "Nachfolger endet frühestens mit dem Vorgänger",
};

/** Welche Art entsteht beim Ziehen? Vom Ende-Anfasser: linke Haelfte des
 * Ziels -> Ende -> Anfang, rechte Haelfte -> Ende -> Ende. Vom Anfang-
 * Anfasser: nur auf den Anfang (linke Haelfte) -> Anfang -> Anfang; Anfang ->
 * Ende gibt es nicht (null). */
export function verbindungsArtBeimZiehen(seite: "anfang" | "ende", ziel: BalkenRechteck, x: number): ZeitplanAbhaengigkeitArt | null {
  const rechteHaelfte = x > ziel.x + ziel.w / 2;
  if (seite === "anfang") return rechteHaelfte ? null : "anfang_anfang";
  return rechteHaelfte ? "ende_ende" : "ende_anfang";
}

// --- Dispo-Termine ---------------------------------------------------------------------

/** Kalendertag (lokale Uhr) eines Termin-Zeitstempels. */
export function terminTag(t: ZeitplanTermin): number {
  return heuteTag(new Date(t.start));
}

export function terminLabel(t: ZeitplanTermin): string {
  const d = new Date(t.start);
  const zeit = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  return `Termin ${formatKurz(terminTag(t))} ${zeit}${t.techniker_name ? ` · ${t.techniker_name}` : ""}`;
}

/** Termin ausserhalb des Plan-Zeitraums des Schritts (Termin passt nicht zum Plan). */
export function terminAusserhalb(t: ZeitplanTermin, z: Zeitraum): boolean {
  const tag = terminTag(t);
  return tag < z.start || tag > z.ende;
}

// --- Standardwerte beim Anlegen ------------------------------------------------------

/** Standard-Start fuer ein neues Element: Ende des letzten datierten
 * Elements der Gruppe + 1 Tag, sonst heute. */
export function standardStart(elemente: ZeitplanElement[], phaseId: string | null, heute: number): number {
  let letztes: number | null = null;
  for (const e of elemente) {
    if (e.typ === "phase" || (e.phase_id ?? null) !== phaseId) continue;
    const z = elementZeitraum(e);
    if (z && (letztes === null || z.ende > letztes)) letztes = z.ende;
  }
  return letztes === null ? heute : letztes + 1;
}

export const SCHRITT_STANDARD_DAUER = 3;

// --- Zeilen der Liste/Zeitleiste -----------------------------------------------------

export interface Entwurf {
  typ: ZeitplanTyp;
  phaseId: string | null;
}

export type Zeile =
  | { art: "element"; element: ZeitplanElement; ebene: 0 | 1 }
  | { art: "entwurf"; typ: ZeitplanTyp; phaseId: string | null }
  | { art: "neu"; phaseId: string | null };

function nachReihenfolge(a: ZeitplanElement, b: ZeitplanElement): number {
  return a.plan_reihenfolge - b.plan_reihenfolge || (a.start_am ?? "9999").localeCompare(b.start_am ?? "9999");
}

/** Flache Zeilenliste: Phasen (auf-/zuklappbar) mit ihren Kindern, danach
 * Elemente ohne Phase; am Ende jeder Gruppe eine "+ anlegen"-Zeile, am Ende
 * eine Fusszeile (phaseId null) fuer Phase/Schritt/Meilenstein ohne Phase. */
export function baueZeilen(elemente: ZeitplanElement[], eingeklappt: Set<string>, entwurf: Entwurf | null): Zeile[] {
  const phasen = elemente.filter((e) => e.typ === "phase").sort(nachReihenfolge);
  const phasenIds = new Set(phasen.map((p) => p.id));
  const zeilen: Zeile[] = [];
  for (const p of phasen) {
    zeilen.push({ art: "element", element: p, ebene: 0 });
    if (eingeklappt.has(p.id)) continue;
    for (const k of elemente.filter((e) => e.typ !== "phase" && e.phase_id === p.id).sort(nachReihenfolge)) {
      zeilen.push({ art: "element", element: k, ebene: 1 });
    }
    if (entwurf && entwurf.typ !== "phase" && entwurf.phaseId === p.id) zeilen.push({ art: "entwurf", typ: entwurf.typ, phaseId: p.id });
    zeilen.push({ art: "neu", phaseId: p.id });
  }
  if (entwurf?.typ === "phase") zeilen.push({ art: "entwurf", typ: "phase", phaseId: null });
  for (const e of elemente.filter((e) => e.typ !== "phase" && (!e.phase_id || !phasenIds.has(e.phase_id))).sort(nachReihenfolge)) {
    zeilen.push({ art: "element", element: e, ebene: 0 });
  }
  if (entwurf && entwurf.typ !== "phase" && entwurf.phaseId === null) zeilen.push({ art: "entwurf", typ: entwurf.typ, phaseId: null });
  zeilen.push({ art: "neu", phaseId: null });
  return zeilen;
}
