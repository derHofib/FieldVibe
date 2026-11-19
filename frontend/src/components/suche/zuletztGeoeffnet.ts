import { useCallback, useEffect, useState } from "react";

import { useAuth } from "../../context/AuthContext";
import type { SearchKategorie } from "../../types";

const MAX_EINTRAEGE = 8;
const SCHLUESSEL = "suche.zuletzt";

export interface ZuletztEintrag {
  kategorie: SearchKategorie;
  id: string;
  titel: string;
  untertitel: string;
  /** Roher Status, damit Label/Farbe aus denselben Mappings wie die Treffer kommen. */
  status?: string | null;
}

// Eigener Schlüssel je Nutzer: auf einem geteilten Rechner soll niemand den Verlauf eines anderen sehen.
function schluessel(userId: string): string {
  return `${SCHLUESSEL}.${userId}`;
}

function gueltig(e: unknown): e is ZuletztEintrag {
  if (!e || typeof e !== "object") return false;
  const o = e as Record<string, unknown>;
  return (
    typeof o.kategorie === "string" &&
    typeof o.id === "string" &&
    typeof o.titel === "string" &&
    typeof o.untertitel === "string"
  );
}

export function liesZuletzt(userId: string): ZuletztEintrag[] {
  try {
    const roh = localStorage.getItem(schluessel(userId));
    if (!roh) return [];
    const daten: unknown = JSON.parse(roh);
    return Array.isArray(daten) ? daten.filter(gueltig).slice(0, MAX_EINTRAEGE) : [];
  } catch {
    return [];
  }
}

function schreibe(userId: string, liste: ZuletztEintrag[]): void {
  try {
    localStorage.setItem(schluessel(userId), JSON.stringify(liste));
  } catch {
    // Privates Fenster/Speicher voll: der Verlauf ist nur Komfort.
  }
}

export function merkeZuletzt(userId: string, eintrag: ZuletztEintrag): void {
  const rest = liesZuletzt(userId).filter((e) => !(e.kategorie === eintrag.kategorie && e.id === eintrag.id));
  schreibe(userId, [eintrag, ...rest].slice(0, MAX_EINTRAEGE));
}

export function leereZuletzt(userId: string): void {
  try {
    localStorage.removeItem(schluessel(userId));
  } catch {
    // siehe schreibe
  }
}

/** Verlauf für die Suche (Leerzustand): lesen, leeren. */
export function useZuletztGeoeffnet() {
  const { currentUser } = useAuth();
  const userId = currentUser?.id;
  const [eintraege, setEintraege] = useState<ZuletztEintrag[]>(() => (userId ? liesZuletzt(userId) : []));

  useEffect(() => {
    setEintraege(userId ? liesZuletzt(userId) : []);
  }, [userId]);

  const leeren = useCallback(() => {
    if (!userId) return;
    leereZuletzt(userId);
    setEintraege([]);
  }, [userId]);

  return { eintraege, leeren };
}

/** Für Detailseiten: merkt den Datensatz, sobald er geladen ist (`null` = noch nicht). */
export function useZuletztGeoeffnetMerken(eintrag: ZuletztEintrag | null): void {
  const { currentUser } = useAuth();
  const userId = currentUser?.id;
  const kategorie = eintrag?.kategorie;
  const id = eintrag?.id;
  const titel = eintrag?.titel;
  const untertitel = eintrag?.untertitel;
  const status = eintrag?.status ?? null;

  useEffect(() => {
    if (!userId || !kategorie || !id || !titel) return;
    merkeZuletzt(userId, { kategorie, id, titel, untertitel: untertitel ?? "", status });
  }, [userId, kategorie, id, titel, untertitel, status]);
}
