import type { Zeiterfassung, ZeiterfassungBuchungsstatus } from "../types";
import { ZEITERFASSUNG_KATEGORIE_LABEL } from "./zeiterfassung";

export interface Gruppe {
  key: string;
  vorgangId: string | null;
  vorgangsnummer: string | null;
  kategorieLabel: string | null;
  kontext: string | null;
  eintraege: Zeiterfassung[];
}

export function gruppenBilden(
  eintraege: Zeiterfassung[],
  kunden: { id: string; name: string }[] | undefined,
  auftraege: { id: string; titel: string }[] | undefined,
  projekte: { id: string; name: string }[] | undefined,
): Gruppe[] {
  const map = new Map<string, Gruppe>();
  for (const e of eintraege) {
    const key = e.vorgang_id ?? `kategorie:${e.kategorie}`;
    let gruppe = map.get(key);
    if (!gruppe) {
      const kontextTeile = [
        e.vorgang_kunde_id ? kunden?.find((k) => k.id === e.vorgang_kunde_id)?.name : undefined,
        e.vorgang_auftrag_id ? auftraege?.find((a) => a.id === e.vorgang_auftrag_id)?.titel : undefined,
        e.vorgang_projekt_id ? projekte?.find((p) => p.id === e.vorgang_projekt_id)?.name : undefined,
      ].filter((teil): teil is string => !!teil);
      gruppe = {
        key,
        vorgangId: e.vorgang_id,
        vorgangsnummer: e.vorgangsnummer,
        kategorieLabel: e.vorgang_id ? null : (ZEITERFASSUNG_KATEGORIE_LABEL[e.kategorie] ?? e.kategorie),
        kontext: kontextTeile.length > 0 ? kontextTeile.join(" · ") : null,
        eintraege: [],
      };
      map.set(key, gruppe);
    }
    gruppe.eintraege.push(e);
  }
  return [...map.values()].sort((a, b) => (a.vorgangsnummer ?? a.kategorieLabel ?? "").localeCompare(b.vorgangsnummer ?? b.kategorieLabel ?? ""));
}

// Nur für beendete Einträge aufrufen: laufende haben kein ende_at.
export const dauerSekunden = (e: Zeiterfassung) => (new Date(e.ende_at!).getTime() - new Date(e.start_at).getTime()) / 1000;

export const summeSekunden = (liste: Zeiterfassung[]) => liste.reduce((s, e) => s + dauerSekunden(e), 0);

export function gruppenSumme(gruppe: Gruppe): number {
  return summeSekunden(gruppe.eintraege);
}

export type ZeitenSortierung = { key: "datum" | "techniker" | "vorgang" | "dauer"; absteigend: boolean };

const collator = new Intl.Collator("de");

export function sortiereEintraege(
  liste: Zeiterfassung[],
  s: ZeitenSortierung,
  technikerName: (id: string) => string,
): Zeiterfassung[] {
  const vergleich = (a: Zeiterfassung, b: Zeiterfassung): number => {
    switch (s.key) {
      case "datum":
        return new Date(a.start_at).getTime() - new Date(b.start_at).getTime();
      case "techniker":
        return collator.compare(technikerName(a.techniker_id), technikerName(b.techniker_id));
      case "vorgang":
        return collator.compare(
          a.vorgangsnummer ?? ZEITERFASSUNG_KATEGORIE_LABEL[a.kategorie] ?? a.kategorie,
          b.vorgangsnummer ?? ZEITERFASSUNG_KATEGORIE_LABEL[b.kategorie] ?? b.kategorie,
        );
      case "dauer":
        return dauerSekunden(a) - dauerSekunden(b);
    }
  };
  // Zweitschlüssel bleibt immer aufsteigend, damit die Reihenfolge bei Gleichstand stabil ist.
  return [...liste].sort((a, b) => {
    const haupt = vergleich(a, b);
    if (haupt !== 0) return s.absteigend ? -haupt : haupt;
    return new Date(a.start_at).getTime() - new Date(b.start_at).getTime();
  });
}

/** Kopf-Checkbox: alle auswählbaren sichtbaren Einträge mit dem Status der bestehenden Auswahl, ohne Auswahl den Status des ersten auswählbaren sichtbaren Eintrags. abgerechnet nie. */
export function alleAuswaehlbarenIds(
  sichtbar: Zeiterfassung[],
  ausgewaehlterStatus: ZeiterfassungBuchungsstatus | null,
): Set<string> {
  const auswaehlbar = sichtbar.filter((e) => e.buchungsstatus !== "abgerechnet");
  const status = ausgewaehlterStatus ?? auswaehlbar[0]?.buchungsstatus ?? null;
  return new Set(auswaehlbar.filter((e) => e.buchungsstatus === status).map((e) => e.id));
}

export function kopfCheckboxZustand(
  sichtbar: Zeiterfassung[],
  ausgewaehlt: Set<string>,
  ausgewaehlterStatus: ZeiterfassungBuchungsstatus | null,
): "aus" | "teilweise" | "an" {
  const ids = alleAuswaehlbarenIds(sichtbar, ausgewaehlterStatus);
  let treffer = 0;
  for (const id of ids) if (ausgewaehlt.has(id)) treffer++;
  if (ids.size > 0 && treffer === ids.size) return "an";
  return treffer > 0 ? "teilweise" : "aus";
}
