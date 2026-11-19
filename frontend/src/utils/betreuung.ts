import type { Betreuer, BetreuerKandidat, KundeBetreuungKurz } from "../types";

export interface BetreuungAuswahl {
  userIds: string[];
  hauptId: string | null;
}

export function auswahlAusBetreuung(betreuung: Betreuer[]): BetreuungAuswahl {
  return {
    userIds: betreuung.map((b) => b.user_id),
    hauptId: betreuung.find((b) => b.hauptbetreuer)?.user_id ?? null,
  };
}

export function betreuerUmschalten(a: BetreuungAuswahl, id: string): BetreuungAuswahl {
  if (a.userIds.includes(id)) {
    return { userIds: a.userIds.filter((u) => u !== id), hauptId: a.hauptId === id ? null : a.hauptId };
  }
  return { ...a, userIds: [...a.userIds, id] };
}

/** Stern setzen: wählt die Person mit an und nimmt ihn dem bisherigen Hauptbetreuer; erneut tippen nimmt ihn weg. */
export function hauptbetreuerUmschalten(a: BetreuungAuswahl, id: string): BetreuungAuswahl {
  if (a.hauptId === id) return { ...a, hauptId: null };
  return { userIds: a.userIds.includes(id) ? a.userIds : [...a.userIds, id], hauptId: id };
}

/** Bisherige Betreuer, die den Kunden nach dem Speichern nicht mehr sehen. */
export function sichtverlust(bisher: Betreuer[], a: BetreuungAuswahl): Betreuer[] {
  return bisher.filter((b) => b.nur_betreute_kunden && !a.userIds.includes(b.user_id));
}

/** Zeilen des Auswahl-Sheets: aktive Kandidaten plus bisherige Betreuer (auch deaktivierte, damit sie abwählbar bleiben). */
export function kandidatenBilden(alle: BetreuerKandidat[] | undefined, bisher: Betreuer[]): BetreuerKandidat[] {
  const bisherIds = new Set(bisher.map((b) => b.user_id));
  const liste = (alle ?? []).filter((k) => k.aktiv || bisherIds.has(k.user_id));
  for (const b of bisher) {
    if (liste.some((k) => k.user_id === b.user_id)) continue;
    liste.push({
      user_id: b.user_id,
      name: b.name,
      avatar_url: b.avatar_url,
      aktiv: b.aktiv,
      nur_betreute_kunden: b.nur_betreute_kunden,
      account_typ_name: b.account_typ_name,
      anzahl_kunden: 0,
    });
  }
  return liste.sort((x, y) => x.name.localeCompare(y.name, "de"));
}

export function betreuungUnterzeile(b: Betreuer): string {
  return [b.hauptbetreuer ? "Hauptbetreuer" : "Vertretung", b.account_typ_name, b.nur_betreute_kunden ? "sieht nur betreute Kunden" : null]
    .filter(Boolean)
    .join(" · ");
}

export function hauptbetreuerVon(betreuung: KundeBetreuungKurz[] | undefined): KundeBetreuungKurz | undefined {
  return betreuung?.find((b) => b.hauptbetreuer);
}

export function betreuungSuchtext(betreuung: KundeBetreuungKurz[] | undefined): string {
  return (betreuung ?? []).map((b) => b.name).join(" ");
}

export const BETREUUNG_OHNE = "Ohne Betreuung";

/** Filter-Wert/-Optionen der Felder "Betreuung" und "Hauptbetreuer" (Typ person). */
export function betreuungFilterWert(betreuung: KundeBetreuungKurz[] | undefined): string[] {
  return (betreuung ?? []).map((b) => b.user_id);
}

export function hauptbetreuerFilterWert(betreuung: KundeBetreuungKurz[] | undefined): string | null {
  return hauptbetreuerVon(betreuung)?.user_id ?? null;
}

/** Optionen: zuerst "Ich", dann alle Mitarbeiter aus Mitarbeiterliste bzw. – ohne diese – aus den geladenen Kunden. */
export function betreuungFilterOptionen(
  eigeneId: string | undefined,
  mitarbeiter: { id: string; name: string }[] | undefined,
  kunden: { betreuung?: KundeBetreuungKurz[] }[] | undefined,
): { wert: string; label: string }[] {
  const personen = new Map<string, string>();
  for (const m of mitarbeiter ?? []) personen.set(m.id, m.name);
  for (const k of kunden ?? []) for (const b of k.betreuung ?? []) if (!personen.has(b.user_id)) personen.set(b.user_id, b.name);
  const rest = [...personen.entries()]
    .filter(([id]) => id !== eigeneId)
    .sort((a, b) => a[1].localeCompare(b[1], "de"))
    .map(([wert, label]) => ({ wert, label }));
  return eigeneId ? [{ wert: eigeneId, label: "Ich" }, ...rest] : rest;
}
