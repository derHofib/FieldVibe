import type { IconTone } from "../components/IconBadge";
import type {
  Rechnung,
  RechnungAusAngebotCreate,
  RechnungGutschriftCreate,
  RechnungPosition,
  Rechnungsart,
} from "../types";
import { formatEuro } from "./format";

export const RECHNUNGSART_LABEL: Record<Rechnungsart, string> = {
  rechnung: "Rechnung",
  abschlag: "Abschlagsrechnung",
  schluss: "Schlussrechnung",
  gutschrift: "Gutschrift",
};

// Normale Rechnung bewusst neutral; Abschlag/Schluss/Gutschrift bekommen je
// einen eigenen Kategorie-Ton, damit sie sich in Listen vom Status-Badge
// (Entwurf/Versendet/...) unterscheiden.
export const RECHNUNGSART_TONE: Record<Rechnungsart, IconTone> = {
  rechnung: "slate",
  abschlag: "indigo",
  schluss: "teal",
  gutschrift: "violet",
};

export const RECHNUNGSART_FILTER: Rechnungsart[] = ["rechnung", "abschlag", "schluss", "gutschrift"];

export const GUTSCHRIFT_GRUND_MIN = 3;
export const GUTSCHRIFT_GRUND_MAX = 200;

/** Altdaten und Antworten ohne Feld sind normale Rechnungen. */
export function rechnungsartVon(rechnung: Pick<Rechnung, "rechnungsart">): Rechnungsart {
  return rechnung.rechnungsart ?? "rechnung";
}

// --- Dezimalrechnung -------------------------------------------------------
// Beträge/Mengen kommen als Decimal-Strings. Float würde bei der
// Prozent-Vorschau um einen Cent von der Server-Rundung (ROUND_HALF_UP)
// abweichen, deshalb exakte BigInt-Arithmetik.

interface Dezimal {
  n: bigint;
  skala: number;
}

const DEZIMAL_MUSTER = /^-?\d+(?:[.,]\d+)?$/;

function parseDezimal(text: string): Dezimal | null {
  const t = text.trim();
  if (!DEZIMAL_MUSTER.test(t)) return null;
  const [ganz, nach = ""] = t.replace(",", ".").split(".");
  return { n: BigInt(ganz + nach), skala: nach.length };
}

function mal(a: Dezimal, b: Dezimal): Dezimal {
  return { n: a.n * b.n, skala: a.skala + b.skala };
}

/** Auf ganze Cent, kaufmännisch (ab .5 weg von null) wie `runde_cent` im Backend. */
function zuCent(wert: Dezimal): bigint {
  const ziel = 2;
  if (wert.skala <= ziel) return wert.n * 10n ** BigInt(ziel - wert.skala);
  const teiler = 10n ** BigInt(wert.skala - ziel);
  const betrag = wert.n < 0n ? -wert.n : wert.n;
  const gerundet = (betrag + teiler / 2n) / teiler;
  return wert.n < 0n ? -gerundet : gerundet;
}

export function centZuText(cent: bigint): string {
  const negativ = cent < 0n;
  const betrag = negativ ? -cent : cent;
  const text = `${betrag / 100n}.${String(betrag % 100n).padStart(2, "0")}`;
  return negativ ? `-${text}` : text;
}

function textZuCent(text: string): bigint | null {
  const d = parseDezimal(text);
  return d ? zuCent(d) : null;
}

// --- Abschlag --------------------------------------------------------------

export type AbschlagModus = "prozent" | "netto";

export interface AbschlagVorschau {
  /** Abschlagsbetrag netto ("123.45") oder null, solange die Eingabe nicht auswertbar ist. */
  betrag: string | null;
  /** Rest des Angebots nach diesem Abschlag. */
  restNachher: string | null;
  /** Deutsche Meldung, wenn die Eingabe unzulässig ist; sonst null. */
  fehler: string | null;
}

/** Prozent -> Netto-Betrag, gerundet wie der Server (`angebot_netto * prozent / 100`). */
export function abschlagNettoAusProzent(angebotNetto: string, prozent: string): string | null {
  const netto = parseDezimal(angebotNetto);
  const p = parseDezimal(prozent);
  if (!netto || !p) return null;
  const roh = mal(netto, p);
  return centZuText(zuCent({ n: roh.n, skala: roh.skala + 2 }));
}

/** Vorschau und Plausibilitätsprüfung für das Abschlag-Sheet. `restNetto` ist der
 * laut Server noch nicht abgerechnete Teil des Angebots. */
export function abschlagVorschau(
  modus: AbschlagModus,
  eingabe: string,
  angebotNetto: string,
  restNetto: string,
): AbschlagVorschau {
  const leer: AbschlagVorschau = { betrag: null, restNachher: null, fehler: null };
  if (!eingabe.trim()) return leer;
  const wert = parseDezimal(eingabe);
  if (!wert || wert.n <= 0n) {
    return { ...leer, fehler: "Bitte eine Zahl größer als 0 eingeben" };
  }
  if (modus === "prozent" && wert.n > 100n * 10n ** BigInt(wert.skala)) {
    return { ...leer, fehler: "Der Prozentsatz darf höchstens 100 % betragen" };
  }
  const betrag =
    modus === "prozent" ? textZuCent(abschlagNettoAusProzent(angebotNetto, eingabe) ?? "") : zuCent(wert);
  const rest = textZuCent(restNetto);
  if (betrag === null || rest === null) return leer;
  if (betrag <= 0n) {
    return { betrag: centZuText(betrag), restNachher: null, fehler: "Der Abschlagsbetrag muss größer als 0 sein" };
  }
  const restNachher = rest - betrag;
  if (restNachher < 0n) {
    return {
      betrag: centZuText(betrag),
      restNachher: centZuText(restNachher),
      fehler: `Mit diesem Abschlag wären mehr als 100 % des Angebots abgerechnet (Rest: ${formatEuro(
        centZuText(rest < 0n ? 0n : rest),
      )})`,
    };
  }
  return { betrag: centZuText(betrag), restNachher: centZuText(restNachher), fehler: null };
}

/** Body für POST /api/rechnungen/aus-angebot (Abschlag): genau eines von
 * abschlag_prozent/abschlag_netto, Dezimalkomma wird zum Punkt. */
export function abschlagPayload(
  angebotId: string,
  modus: AbschlagModus,
  eingabe: string,
  faelligAm: string,
): RechnungAusAngebotCreate {
  const wert = eingabe.trim().replace(",", ".");
  return {
    angebot_id: angebotId,
    rechnungsart: "abschlag",
    ...(modus === "prozent" ? { abschlag_prozent: wert } : { abschlag_netto: wert }),
    ...(faelligAm ? { faellig_am: faelligAm } : {}),
  };
}

// --- Gutschrift ------------------------------------------------------------

export function istAbzugsposition(position: Pick<RechnungPosition, "abschlag_rechnung_id">): boolean {
  return !!position.abschlag_rechnung_id;
}

const GUTSCHRIFT_STATUS = new Set(["versendet", "teilweise_bezahlt", "bezahlt"]);

/** Zustandsprädikat ohne Rechteprüfung (die liegt an der Seite, `abrechnung/erstellen`). */
export function kannGutschriftErstellen(
  rechnung: Pick<Rechnung, "status" | "ist_storno" | "rechnungsart">,
): boolean {
  const art = rechnung.rechnungsart ?? "rechnung";
  return (art === "rechnung" || art === "schluss") && !rechnung.ist_storno && GUTSCHRIFT_STATUS.has(rechnung.status);
}

/** Menge minus bereits gutgeschrieben, nie negativ -- unabhängig von der Positionsart. */
export function restMenge(position: Pick<RechnungPosition, "menge" | "bereits_gutgeschrieben">): number {
  const menge = textZuCent(position.menge);
  const bereits = textZuCent(position.bereits_gutgeschrieben ?? "0");
  if (menge === null || bereits === null) return 0;
  const rest = menge - bereits;
  return rest > 0n ? Number(rest) / 100 : 0;
}

/** Bei Teil-Gutschriften wählbare Höchstmenge. Abzugspositionen einer Schlussrechnung
 * sind nicht einzeln gutschreibbar (nur über "Komplett"). */
export function maxGutschriftMenge(
  position: Pick<RechnungPosition, "menge" | "bereits_gutgeschrieben" | "abschlag_rechnung_id">,
): number {
  return istAbzugsposition(position) ? 0 : restMenge(position);
}

/** Menge deutsch/englisch tippbar -> Zahl; null bei Unsinn oder <= 0. */
export function parseMenge(text: string): number | null {
  const cent = textZuCent(text);
  return cent !== null && cent > 0n ? Number(cent) / 100 : null;
}

/** Position-ID -> eingegebene Menge (Text); nur ausgewählte Positionen. */
export type GutschriftAuswahl = Record<string, string>;

/** Fehlermeldung zu einer gewählten Menge (null = ok). */
export function gutschriftMengeFehler(position: RechnungPosition, eingabe: string): string | null {
  const menge = parseMenge(eingabe);
  if (menge === null) return "Menge größer als 0 eingeben";
  const max = maxGutschriftMenge(position);
  if (menge > max) return `Höchstens ${max.toLocaleString("de-DE", { maximumFractionDigits: 2 })} ${position.einheit}`;
  return null;
}

export interface GutschriftSumme {
  netto: string;
  steuer: string;
  brutto: string;
}

/** Summe einer (Teil-)Gutschrift mit Vorzeichen minus, nach demselben Schema wie der
 * Server: je Steuergruppe Menge*Preis summieren, auf Cent runden, dann Steuer. */
export function gutschriftSumme(
  positionen: { position: RechnungPosition; menge: string }[],
  belegMwstSatz: string,
): GutschriftSumme {
  const gruppen = new Map<string, { roh: Dezimal; satz: Dezimal }>();
  for (const { position, menge } of positionen) {
    const m = parseDezimal(menge);
    const preis = parseDezimal(position.einzelpreis);
    const satz = parseDezimal(position.steuer_satz ?? belegMwstSatz) ?? { n: 0n, skala: 0 };
    if (!m || !preis) continue;
    const schluessel = `${position.steuer_kategorie ?? ""}|${satz.n}|${satz.skala}`;
    // Gutschrift nimmt zurück: Preis der Originalposition mit umgekehrtem Vorzeichen.
    const posten = mal(m, { n: -preis.n, skala: preis.skala });
    const bisher = gruppen.get(schluessel);
    if (!bisher) {
      gruppen.set(schluessel, { roh: posten, satz });
    } else {
      const skala = Math.max(bisher.roh.skala, posten.skala);
      const a = bisher.roh.n * 10n ** BigInt(skala - bisher.roh.skala);
      const b = posten.n * 10n ** BigInt(skala - posten.skala);
      bisher.roh = { n: a + b, skala };
    }
  }
  let netto = 0n;
  let steuer = 0n;
  for (const { roh, satz } of gruppen.values()) {
    const nettoGruppe = zuCent(roh);
    netto += nettoGruppe;
    steuer += zuCent({ n: nettoGruppe * satz.n, skala: satz.skala + 2 + 2 });
  }
  return { netto: centZuText(netto), steuer: centZuText(steuer), brutto: centZuText(netto + steuer) };
}

/** Body für POST /api/rechnungen/{id}/gutschrift. */
export function gutschriftPayload(
  modus: "alle" | "positionen",
  auswahl: GutschriftAuswahl,
  grund: string,
): RechnungGutschriftCreate {
  if (modus === "alle") return { alle: true, grund: grund.trim() };
  return {
    positionen: Object.entries(auswahl).map(([position_id, menge]) => ({
      position_id,
      menge: menge.trim().replace(",", "."),
    })),
    grund: grund.trim(),
  };
}

export function gutschriftGrundFehler(grund: string): string | null {
  const laenge = grund.trim().length;
  if (laenge < GUTSCHRIFT_GRUND_MIN) return `Mindestens ${GUTSCHRIFT_GRUND_MIN} Zeichen`;
  if (laenge > GUTSCHRIFT_GRUND_MAX) return `Höchstens ${GUTSCHRIFT_GRUND_MAX} Zeichen`;
  return null;
}

// --- Offener Betrag --------------------------------------------------------

/** Negativer offener Betrag (Gutschrift bzw. Überzahlung) ist ein Guthaben. */
export function offenLabel(offenerBetrag: string): string {
  return Number(offenerBetrag) < 0 ? "Guthaben" : "Offen";
}

/** Betrag als Anzeige-Wert ohne Vorzeichen-Verwechslung: Guthaben positiv ausweisen. */
export function offenAnzeige(offenerBetrag: string): string {
  const zahl = Number(offenerBetrag);
  return Number.isNaN(zahl) ? offenerBetrag : Math.abs(zahl).toFixed(2);
}
