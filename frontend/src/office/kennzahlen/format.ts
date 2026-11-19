import type { KennzahlEinheit } from "../../types/kennzahlen";
import { richtungFuer } from "./darstellungen";

const NBSP = " ";

const zahl = (max: number, min = 0) => new Intl.NumberFormat("de-DE", { minimumFractionDigits: min, maximumFractionDigits: max });
const GANZZAHL = zahl(0);
const EINE_STELLE = zahl(1);
const EURO_CENT = new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" });
const EURO_GLATT = new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });

export const KEIN_WERT = "–";

/** Ab 10.000 € stören Cent nur noch beim Vergleichen (Kachel "48.320 €"), darunter bleiben sie sichtbar. */
export function formatEuroKennzahl(wert: number): string {
  return (Math.abs(wert) >= 10_000 ? EURO_GLATT : EURO_CENT).format(wert);
}

export function formatMinuten(minuten: number): string {
  const gerundet = Math.round(minuten);
  const stunden = Math.floor(Math.abs(gerundet) / 60);
  const rest = Math.abs(gerundet) % 60;
  const vorzeichen = gerundet < 0 ? "-" : "";
  if (stunden === 0) return `${vorzeichen}${rest} min`;
  return rest === 0 ? `${vorzeichen}${stunden} h` : `${vorzeichen}${stunden} h ${rest} min`;
}

/** Ein Wert samt Einheit, deutsch formatiert. null (keine Daten) wird zu "–", nie zu "0". */
export function formatWert(wert: number | null | undefined, einheit: KennzahlEinheit): string {
  if (wert === null || wert === undefined || Number.isNaN(wert)) return KEIN_WERT;
  switch (einheit) {
    case "eur":
      return formatEuroKennzahl(wert);
    case "anzahl":
      return GANZZAHL.format(wert);
    case "tage":
      return `${EINE_STELLE.format(wert)}${NBSP}${Math.abs(wert) === 1 ? "Tag" : "Tage"}`;
    case "prozent":
      return `${EINE_STELLE.format(wert)}${NBSP}%`;
    case "minuten":
      return formatMinuten(wert);
  }
}

/** Kompakte Achsenbeschriftung ("12 Tsd.", "1,2 Mio."). Nur Beträge und große Zahlen kürzen; Zeiten/Quoten bleiben lesbar. */
export function formatAchse(wert: number, einheit: KennzahlEinheit): string {
  const betrag = Math.abs(wert);
  if (einheit === "eur" || einheit === "anzahl") {
    if (betrag >= 1_000_000) return `${EINE_STELLE.format(wert / 1_000_000)}${NBSP}Mio.`;
    if (betrag >= 1_000) return `${einheit === "eur" && betrag < 10_000 ? EINE_STELLE.format(wert / 1_000) : GANZZAHL.format(wert / 1_000)}${NBSP}Tsd.`;
  }
  if (einheit === "minuten") return formatMinuten(wert);
  return EINE_STELLE.format(wert);
}

export interface Abweichung {
  text: string;
  /** Nur Pfeil und Betrag, ohne "ggü. ..." (Tabellenspalte). */
  kurz: string;
  richtung: "hoch" | "runter" | "gleich";
  /** true = positiv zu werten, false = negativ, null = neutral (Kennzahl ohne klare Richtung). */
  gut: boolean | null;
}

/** "▲ 12 % ggü. Oktober": Pfeil steht als Text im Satz, Farbe allein trägt die Aussage nie.
 * Anzahlen/Tage/Prozentwerte zeigen die absolute Differenz (Prozent von 3 auf 5 wäre irreführend),
 * Beträge/Minuten die relative Veränderung. Ohne Vergleichswert gibt es keine Abweichung. */
export function abweichung(
  kennzahl: string,
  einheit: KennzahlEinheit,
  wert: number | null,
  vorperiode: number | null,
  vorLabel: string,
): Abweichung | null {
  if (wert === null || vorperiode === null) return null;
  const differenz = wert - vorperiode;
  if (Math.abs(differenz) < 1e-9) return { text: `= unverändert ggü.${NBSP}${vorLabel}`, kurz: "= unverändert", richtung: "gleich", gut: null };

  const hoch = differenz > 0;
  let betrag: string;
  if (einheit === "eur" || einheit === "minuten") {
    betrag =
      vorperiode === 0
        ? formatWert(Math.abs(differenz), einheit)
        : `${GANZZAHL.format(Math.abs(differenz / vorperiode) * 100)}${NBSP}%`;
  } else if (einheit === "prozent") {
    betrag = `${EINE_STELLE.format(Math.abs(differenz))}${NBSP}Punkte`;
  } else {
    betrag = formatWert(Math.abs(differenz), einheit);
  }

  const richtung = richtungFuer(kennzahl);
  const gut = richtung === "neutral" ? null : hoch === (richtung === "hoeher_besser");
  const kurz = `${hoch ? "▲" : "▼"} ${betrag}`;
  return { text: `${kurz} ggü.${NBSP}${vorLabel}`, kurz, richtung: hoch ? "hoch" : "runter", gut };
}
