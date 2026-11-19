import { VORGANG_STATUS_LABEL, vorgangStatusZuToken } from "../../../components/apple/status";
import type { KennzahlDaten, KennzahlEinheit, KennzahlZeile, WidgetGroesse } from "../../../types/kennzahlen";
import type { VorgangStatus } from "../../../types";

/** Gemeinsame Props aller Darstellungen: reine Anzeige, die Daten kommen fertig von der WidgetKarte. */
export interface DarstellungProps {
  daten: KennzahlDaten;
  groesse: WidgetGroesse;
  /** Vorperiode mit anzeigen (nur wirksam, wenn die Zeilen/Gesamtwerte eine Vorperiode mitbringen). */
  vergleich: boolean;
  /** Zeilen sind Vorgangs-Status und bekommen die Status-Farben statt der Akzentfarbe. */
  statusFarben: boolean;
  /** false: Teile ergeben keine Summe (Durchlaufzeit, Quoten) -- kein "Weitere", kein Gesamt. */
  summierbar: boolean;
  /** Anzeigetitel, für die Kurzbeschreibung (aria-label) der Diagramme. */
  titel: string;
  /** Bezeichnung der Vorperiode ("Oktober", "Vorwoche"). */
  vorLabel: string;
  /** Beschriftung des aktuellen Zeitraums ("November 2026", "Stand heute"); Legende und Tabellenkopf. */
  zeitraumLabel?: string;
  /** Name der Aufteilung ("Kunde"); Kopf der ersten Tabellenspalte. */
  gruppierungLabel?: string;
}

export const AKZENT = "var(--tint)";
export const VORPERIODE_FARBE = "var(--fill2)";

export function hatVorperiode(daten: KennzahlDaten, vergleich: boolean): boolean {
  return vergleich && daten.zeilen.some((z) => z.vorperiode !== null);
}

/** Farbe eines Vorgangs-Status als CSS-Variable (statt statusDotFarbe(): so folgt sie ohne Neuberechnen dem Hell/Dunkel-Wechsel). */
export function statusFarbe(schluessel: string): string | null {
  if (!(schluessel in VORGANG_STATUS_LABEL)) return null;
  return `var(--st-${vorgangStatusZuToken(schluessel as VorgangStatus)}-dot)`;
}

export function zeilenFarbe(zeile: KennzahlZeile, statusFarben: boolean): string {
  return (statusFarben ? statusFarbe(zeile.schluessel) : null) ?? AKZENT;
}

/** Alter überfälliger Posten: nicht fällige Töne in Akzent, danach von Orange zu Rot. Welche Zeilen "nicht fällig" sind,
 * entscheidet der Schlüssel/das Label (Backend benennt die Buckets), nicht die Position allein. */
export function alterFarben(zeilen: KennzahlZeile[]): string[] {
  const nichtFaellig = (z: KennzahlZeile) => /nicht/i.test(`${z.schluessel} ${z.label}`);
  const ersteUeberfaellig = Math.max(0, zeilen.findIndex((z) => !nichtFaellig(z)));
  return zeilen.map((_, i) => {
    if (i < ersteUeberfaellig) return AKZENT;
    return i - ersteUeberfaellig < 2 ? "var(--st-arbeit-dot)" : "var(--st-fehlt-dot)";
  });
}

export function istReihenfolgeFest(gruppierung: string): boolean {
  return gruppierung === "status" || gruppierung === "alter";
}

/** Rangliste: absteigend nach Wert; Status und Alter behalten ihre natürliche Reihenfolge. Zahlen ohne Wert zählen als 0. */
export function sortiert(daten: KennzahlDaten): KennzahlZeile[] {
  if (istReihenfolgeFest(daten.gruppierung)) return [...daten.zeilen];
  return [...daten.zeilen].sort((a, b) => (b.wert ?? 0) - (a.wert ?? 0));
}

const SCHRITTE = [1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10];

/** Obergrenze der y-Achse, so gewählt, dass die drei Hilfslinien runde Werte tragen (z. B. 5/10/15 statt 3,7/7,3/11). */
export function achsenMaximum(hoechster: number, einheit: KennzahlEinheit): number {
  if (!(hoechster > 0)) return einheit === "anzahl" ? 3 : 1;
  const roh = hoechster / 3;
  const zehner = 10 ** Math.floor(Math.log10(roh));
  let schritt = (SCHRITTE.find((s) => s * zehner >= roh) ?? 10) * zehner;
  if (einheit === "anzahl") schritt = Math.max(1, Math.ceil(schritt));
  return schritt * 3;
}

/** Nur jeder n-te x-Wert wird beschriftet, damit lange Zeitreihen nicht überlappen. */
export function beschriftungsAbstand(anzahl: number, groesse: WidgetGroesse): number {
  const maximal = { s: 4, m: 6, l: 10, xl: 20 }[groesse];
  return Math.max(1, Math.ceil(anzahl / maximal));
}

export function hoechsterWert(daten: KennzahlDaten, mitVorperiode: boolean): number {
  let hoechster = 0;
  for (const z of daten.zeilen) {
    hoechster = Math.max(hoechster, z.wert ?? 0, mitVorperiode ? (z.vorperiode ?? 0) : 0);
  }
  return hoechster;
}
