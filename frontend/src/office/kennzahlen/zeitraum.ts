import type { DashboardZeitraum, KennzahlGruppierung } from "../../types/kennzahlen";
import { datumZuIso } from "../../utils/format";

/** Reine Zeitraum-Logik der Kennzahlen: Das Frontend gibt dem Backend Zeitraum und Vorperiode
 * exakt vor (kein serverseitiges "Vorperiode raten"), deshalb steht die Berechnung hier und ist getestet. */

export const ZEITRAUM_OPTIONEN: { wert: DashboardZeitraum; label: string }[] = [
  { wert: "woche", label: "Woche" },
  { wert: "monat", label: "Monat" },
  { wert: "quartal", label: "Quartal" },
  { wert: "jahr", label: "Jahr" },
  { wert: "12_monate", label: "Letzte 12 Monate" },
];

const MONATE_LANG = [
  "Januar", "Februar", "März", "April", "Mai", "Juni",
  "Juli", "August", "September", "Oktober", "November", "Dezember",
];
const MONATE_KURZ = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];

export interface BerechneterZeitraum {
  /** Beide Grenzen inklusive, ISO-Datum (YYYY-MM-DD). */
  von: string;
  bis: string;
  vergleich_von: string;
  vergleich_bis: string;
  label: string;
  /** Bezeichnung der Vorperiode im Vergleichstext ("ggü. Oktober"). */
  vorperiodeLabel: string;
}

/** ISO-8601-Kalenderwoche samt Wochenjahr: um Silvester gehört der Tag ggf. zur KW 1 bzw. 52/53 des Nachbarjahres. */
function isoWoche(datum: Date): { jahr: number; woche: number } {
  const donnerstag = new Date(Date.UTC(datum.getFullYear(), datum.getMonth(), datum.getDate()));
  donnerstag.setUTCDate(donnerstag.getUTCDate() - ((donnerstag.getUTCDay() + 6) % 7) + 3);
  const jahr = donnerstag.getUTCFullYear();
  const jan4 = new Date(Date.UTC(jahr, 0, 4));
  const woche =
    1 + Math.round(((donnerstag.getTime() - jan4.getTime()) / 86_400_000 - 3 + ((jan4.getUTCDay() + 6) % 7)) / 7);
  return { jahr, woche };
}

function addTage(datum: Date, tage: number): Date {
  const ergebnis = new Date(datum.getFullYear(), datum.getMonth(), datum.getDate());
  ergebnis.setDate(ergebnis.getDate() + tage);
  return ergebnis;
}

/** Monate addieren ohne Überlauf (31. Januar + 1 Monat = 28./29. Februar, nicht 3. März). */
function addMonate(datum: Date, monate: number): Date {
  const ziel = new Date(datum.getFullYear(), datum.getMonth() + monate, 1);
  const letzterTag = new Date(ziel.getFullYear(), ziel.getMonth() + 1, 0).getDate();
  ziel.setDate(Math.min(datum.getDate(), letzterTag));
  return ziel;
}

function monatsErster(jahr: number, monat: number): Date {
  return new Date(jahr, monat, 1);
}

function monatsLetzter(jahr: number, monat: number): Date {
  return new Date(jahr, monat + 1, 0);
}

export function zeitraumBerechnen(art: DashboardZeitraum, anker: Date): BerechneterZeitraum {
  const jahr = anker.getFullYear();
  const monat = anker.getMonth();

  switch (art) {
    case "woche": {
      const montag = addTage(anker, -((anker.getDay() + 6) % 7));
      const { jahr: wochenJahr, woche } = isoWoche(montag);
      return {
        von: datumZuIso(montag),
        bis: datumZuIso(addTage(montag, 6)),
        vergleich_von: datumZuIso(addTage(montag, -7)),
        vergleich_bis: datumZuIso(addTage(montag, -1)),
        label: `KW ${woche} ${wochenJahr}`,
        vorperiodeLabel: "Vorwoche",
      };
    }
    case "monat": {
      const vor = monatsErster(jahr, monat - 1);
      return {
        von: datumZuIso(monatsErster(jahr, monat)),
        bis: datumZuIso(monatsLetzter(jahr, monat)),
        vergleich_von: datumZuIso(vor),
        vergleich_bis: datumZuIso(monatsLetzter(vor.getFullYear(), vor.getMonth())),
        label: `${MONATE_LANG[monat]} ${jahr}`,
        vorperiodeLabel: MONATE_LANG[vor.getMonth()],
      };
    }
    case "quartal": {
      const quartal = Math.floor(monat / 3);
      const vor = monatsErster(jahr, quartal * 3 - 3);
      return {
        von: datumZuIso(monatsErster(jahr, quartal * 3)),
        bis: datumZuIso(monatsLetzter(jahr, quartal * 3 + 2)),
        vergleich_von: datumZuIso(vor),
        vergleich_bis: datumZuIso(monatsLetzter(vor.getFullYear(), vor.getMonth() + 2)),
        label: `Q${quartal + 1} ${jahr}`,
        vorperiodeLabel: `Q${Math.floor(vor.getMonth() / 3) + 1} ${vor.getFullYear()}`,
      };
    }
    case "jahr":
      return {
        von: datumZuIso(monatsErster(jahr, 0)),
        bis: datumZuIso(monatsLetzter(jahr, 11)),
        vergleich_von: datumZuIso(monatsErster(jahr - 1, 0)),
        vergleich_bis: datumZuIso(monatsLetzter(jahr - 1, 11)),
        label: String(jahr),
        vorperiodeLabel: String(jahr - 1),
      };
    case "12_monate": {
      // Laufender Monat zählt mit (Dez bis Nov, nicht Nov bis Okt), sonst fehlte immer der aktuellste Monat.
      const start = monatsErster(jahr, monat - 11);
      return {
        von: datumZuIso(start),
        bis: datumZuIso(monatsLetzter(jahr, monat)),
        vergleich_von: datumZuIso(monatsErster(jahr, monat - 23)),
        vergleich_bis: datumZuIso(monatsLetzter(jahr, monat - 12)),
        label: `${MONATE_KURZ[start.getMonth()]} ${start.getFullYear()} – ${MONATE_KURZ[monat]} ${jahr}`,
        vorperiodeLabel: "Vorjahreszeitraum",
      };
    }
  }
}

/** Verschiebt den Anker um einen ganzen Zeitraum (schritt -1 = zurück, +1 = vor). */
export function verschieben(art: DashboardZeitraum, anker: Date, schritt: 1 | -1): Date {
  switch (art) {
    case "woche":
      return addTage(anker, 7 * schritt);
    case "monat":
    case "12_monate":
      return addMonate(anker, schritt);
    case "quartal":
      return addMonate(anker, 3 * schritt);
    case "jahr":
      return addMonate(anker, 12 * schritt);
  }
}

/** "Nächster Zeitraum" ist gesperrt, sobald der angezeigte Zeitraum heute enthält -- die Zukunft hat keine Zahlen. */
export function zeitraumEnthaeltHeute(art: DashboardZeitraum, anker: Date, heute: Date): boolean {
  return zeitraumBerechnen(art, anker).bis >= datumZuIso(heute);
}

/** Zeitachse für Verläufe: kurze Zeiträume wochenweise, lange monatsweise. Gibt null zurück, wenn die Kennzahl keine Zeit-Aufteilung kennt. */
export function zeitGruppierungFuer(art: DashboardZeitraum, gruppierungen: KennzahlGruppierung[]): string | null {
  const zeit = gruppierungen.filter((g) => g.zeit);
  if (zeit.length === 0) return null;
  const wunsch = art === "woche" || art === "monat" ? "woche" : "monat";
  return (zeit.find((g) => g.schluessel === wunsch) ?? zeit[0]).schluessel;
}
