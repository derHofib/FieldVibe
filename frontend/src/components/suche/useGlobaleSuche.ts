import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { type SearchOptionen, searchApi } from "../../api/endpoints";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import type { SearchHit, SearchKategorie } from "../../types";
import { datumZuIso } from "../../utils/format";
import { KATEGORIE_REIHENFOLGE } from "./kategorien";

export type SuchKategorieWahl = "alle" | SearchKategorie;
export type Zeitraum = "beliebig" | "heute" | "7" | "30" | "jahr" | { von: string };

export const ZEITRAUM_OPTIONEN: { wert: Exclude<Zeitraum, { von: string }>; label: string }[] = [
  { wert: "beliebig", label: "Beliebig" },
  { wert: "heute", label: "Heute" },
  { wert: "7", label: "Letzte 7 Tage" },
  { wert: "30", label: "Letzte 30 Tage" },
  { wert: "jahr", label: "Dieses Jahr" },
];

const LIMIT_ALLE = 3;
const LIMIT_KATEGORIE = 25;
const ENTPRELLUNG_MS = 150;

/** Zeitraum → `seit` (YYYY-MM-DD, Lokalzeit). */
export function zeitraumZuSeit(zeitraum: Zeitraum, jetzt: Date = new Date()): string | undefined {
  if (typeof zeitraum === "object") return zeitraum.von || undefined;
  switch (zeitraum) {
    case "beliebig":
      return undefined;
    case "heute":
      return datumZuIso(jetzt);
    case "7":
    case "30": {
      const d = new Date(jetzt);
      d.setDate(d.getDate() - Number(zeitraum));
      return datumZuIso(d);
    }
    case "jahr":
      return `${jetzt.getFullYear()}-01-01`;
  }
}

export interface TrefferGruppe {
  kategorie: SearchKategorie;
  treffer: SearchHit[];
}

function istExakt(hit: SearchHit, begriff: string): boolean {
  const q = begriff.trim().toLowerCase();
  if (!q) return false;
  return hit.nummer?.toLowerCase() === q || hit.titel.toLowerCase().startsWith(q);
}

/** Gruppen mit exaktem Nummern-/Titeltreffer zuerst (wer „V-2026-0142" tippt, sieht den Vorgang oben),
 * sonst feste Reihenfolge. */
export function gruppiereTreffer(treffer: SearchHit[], begriff: string): TrefferGruppe[] {
  const gruppen = KATEGORIE_REIHENFOLGE.map((kategorie) => ({
    kategorie,
    treffer: treffer.filter((t) => t.kategorie === kategorie),
  })).filter((g) => g.treffer.length > 0);
  const exakt = gruppen.filter((g) => g.treffer.some((t) => istExakt(t, begriff)));
  return [...exakt, ...gruppen.filter((g) => !exakt.includes(g))];
}

/** Zustand und Abfrage der globalen Suche, gemeinsam für das Office-Fenster und die Feld-Seite. */
export function useGlobaleSuche(anfangsEingabe = "") {
  const [eingabe, setEingabe] = useState(anfangsEingabe);
  const [kategorie, setKategorie] = useState<SuchKategorieWahl>("alle");
  const [nurOffen, setNurOffen] = useState(false);
  const [zeitraum, setZeitraum] = useState<Zeitraum>("beliebig");
  const [mirZugewiesen, setMirZugewiesen] = useState(false);

  const q = useDebouncedValue(eingabe, ENTPRELLUNG_MS).trim();
  const aktiv = q.length > 0;
  const seit = zeitraumZuSeit(zeitraum);

  const filter: SearchOptionen = { nurOffen, seit, mirZugewiesen };
  const filterKey = [nurOffen, seit ?? "", mirZugewiesen];

  // Die „Alle"-Abfrage läuft immer mit: sie liefert die Zahlen der Kategorie-Pillen, auch wenn eine Kategorie gewählt ist.
  const alle = useQuery({
    queryKey: ["globale-suche", "alle", q, ...filterKey],
    queryFn: () => searchApi.search(q, { ...filter, limit: LIMIT_ALLE }),
    enabled: aktiv,
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  });

  const einzeln = useInfiniteQuery({
    queryKey: ["globale-suche", "kategorie", kategorie, q, ...filterKey],
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      searchApi.search(q, {
        ...filter,
        kategorie: kategorie === "alle" ? undefined : kategorie,
        limit: LIMIT_KATEGORIE,
        offset: pageParam,
      }),
    getNextPageParam: (letzte, seiten) => (letzte.treffer.length >= LIMIT_KATEGORIE ? seiten.length * LIMIT_KATEGORIE : undefined),
    enabled: aktiv && kategorie !== "alle",
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  });

  const gruppen = useMemo<TrefferGruppe[]>(() => {
    if (!aktiv) return [];
    if (kategorie === "alle") return gruppiereTreffer(alle.data?.treffer ?? [], q);
    const treffer = (einzeln.data?.pages ?? []).flatMap((s) => s.treffer).filter((t) => t.kategorie === kategorie);
    return treffer.length > 0 ? [{ kategorie, treffer }] : [];
  }, [aktiv, kategorie, q, alle.data, einzeln.data]);

  const aktuelle = kategorie === "alle" ? alle : einzeln;

  return {
    eingabe,
    setEingabe,
    /** Entprellter, getrimmter Suchbegriff -- das, wonach gerade gesucht wird. */
    begriff: q,
    aktiv,
    kategorie,
    setKategorie,
    nurOffen,
    setNurOffen,
    zeitraum,
    setZeitraum,
    mirZugewiesen,
    setMirZugewiesen,
    gruppen,
    anzahl: aktiv ? alle.data?.anzahl : undefined,
    /** Erste Antwort steht noch aus. */
    laedt: aktiv && aktuelle.isPending,
    /** Zeigt noch das Ergebnis der vorigen Eingabe. */
    veraltet: aktiv && aktuelle.isPlaceholderData,
    fehler: aktuelle.error,
    neuLaden: () => void aktuelle.refetch(),
    hatWeitere: kategorie !== "alle" && !!einzeln.hasNextPage,
    ladeWeitere: () => void einzeln.fetchNextPage(),
    ladeWeitereLaeuft: einzeln.isFetchingNextPage,
  };
}

export type GlobaleSuche = ReturnType<typeof useGlobaleSuche>;
