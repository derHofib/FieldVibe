import type { Eingangsrechnung } from "../types";
import { datumZuIso, tageZwischen } from "./format";

export interface EingangsKennzahlen {
  offen: { summe: number; anzahl: number };
  ueberfaellig: { summe: number; anzahl: number; aeltesteTage: number };
  skonto: { anzahl: number; ersparnis: number };
  bezahltImMonat: { summe: number; anzahl: number };
}

const SKONTO_VORLAUF_TAGE = 7;

/** Reine Funktion auf der bereits geladenen Liste (kein eigener Endpunkt). Vergleich auf
 * Kalendertags-Strings, damit Zeitzone/Uhrzeit von `heute` keine Rolle spielt. */
export function eingangsKennzahlen(liste: Eingangsrechnung[], heute: Date): EingangsKennzahlen {
  const heuteIso = datumZuIso(heute);
  const bis = new Date(heute);
  bis.setDate(bis.getDate() + SKONTO_VORLAUF_TAGE);
  const skontoBis = datumZuIso(bis);
  const monat = heuteIso.slice(0, 7);

  const k: EingangsKennzahlen = {
    offen: { summe: 0, anzahl: 0 },
    ueberfaellig: { summe: 0, anzahl: 0, aeltesteTage: 0 },
    skonto: { anzahl: 0, ersparnis: 0 },
    bezahltImMonat: { summe: 0, anzahl: 0 },
  };

  for (const e of liste) {
    if (e.status === "offen") {
      const offen = Number(e.offener_betrag) || 0;
      k.offen.summe += offen;
      k.offen.anzahl += 1;
      const faellig = e.faellig_am?.slice(0, 10);
      if (faellig && faellig < heuteIso) {
        k.ueberfaellig.summe += offen;
        k.ueberfaellig.anzahl += 1;
        k.ueberfaellig.aeltesteTage = Math.max(k.ueberfaellig.aeltesteTage, tageZwischen(faellig, heuteIso));
      }
      const frist = e.skonto_frist?.slice(0, 10);
      if (frist && frist >= heuteIso && frist <= skontoBis) {
        k.skonto.anzahl += 1;
        k.skonto.ersparnis += Number(e.skonto_betrag) || 0;
      }
    } else if (e.status === "bezahlt" && e.bezahlt_am?.slice(0, 7) === monat) {
      k.bezahltImMonat.summe += Number(e.betrag_brutto) || 0;
      k.bezahltImMonat.anzahl += 1;
    }
  }
  return k;
}
