import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { projektAufgabenApi } from "../../../api/endpoints";
import { filterAnwenden } from "../../../components/filter/auswerten";
import { useFilterZustand } from "../../../components/filter/useFilterZustand";
import { useToast } from "../../../components/Toast";
import type { ProjektAufgabe } from "../../../types";
import { heuteIso } from "../../../utils/format";
import {
  aufgabenFilterFelder,
  eingeklapptLesen,
  eingeklapptSchreiben,
  gruppiereAufgaben,
  gruppierungAusUrl,
  kennzahlen,
  sortiereAufgaben,
  sortierungAusUrl,
  sucheAufgaben,
  STANDARD_GRUPPIERUNG,
  STANDARD_SORTIERUNG,
  type Gruppierung,
  type Sortierung,
} from "./aufgabenLogik";

export type Segment = "offen" | "erledigt";

/** Segment "Erledigt" lädt nur die letzten Tage; der Filter "Erledigt am" wirkt darauf, erweitert sie nicht. */
const ERLEDIGT_TAGE = 90;

/** Gemeinsame Logik von Office-Tabelle und Feld-Karten: Laden, Suche, Filter, Sortierung, Gruppierung.
 * Gruppierung, Sortierung und Segment stehen in der URL (`gruppe`, `sort`, `seg`), eingeklappte Gruppen je
 * Gruppierung im localStorage. */
export function useMeineAufgaben() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const segment: Segment = params.get("seg") === "erledigt" ? "erledigt" : "offen";
  const gruppierung = gruppierungAusUrl(params.get("gruppe"));
  const sortierung = sortierungAusUrl(params.get("sort"));

  const setParam = useCallback(
    (name: string, wert: string | null) =>
      setParams(
        (prev) => {
          const n = new URLSearchParams(prev);
          if (wert) n.set(name, wert);
          else n.delete(name);
          return n;
        },
        { replace: true },
      ),
    [setParams],
  );
  // Standardwerte bleiben aus der URL, damit Links kurz bleiben.
  const setGruppierung = (g: Gruppierung) => setParam("gruppe", g === STANDARD_GRUPPIERUNG ? null : g);
  const setSortierung = (s: Sortierung) => setParam("sort", s === STANDARD_SORTIERUNG ? null : s);
  const setSegment = (s: Segment) => setParam("seg", s === "offen" ? null : s);

  const offenQuery = useQuery({
    queryKey: ["projekt-aufgaben", "meine", "offen"],
    queryFn: () => projektAufgabenApi.list({ mir_zugewiesen: true, erledigt: "offen" }),
  });
  const erledigtQuery = useQuery({
    queryKey: ["projekt-aufgaben", "meine", "erledigt"],
    queryFn: () => projektAufgabenApi.list({ mir_zugewiesen: true, erledigt: "erledigt", erledigt_seit: heuteIso(-ERLEDIGT_TAGE) }),
  });
  const aktiv = segment === "offen" ? offenQuery : erledigtQuery;
  const quelle = useMemo(() => aktiv.data ?? [], [aktiv.data]);

  const felder = useMemo(() => aufgabenFilterFelder(quelle, segment === "erledigt"), [quelle, segment]);
  const zustand = useFilterZustand<ProjektAufgabe>({ felder });
  const { bedingungen, sucheVerzoegert } = zustand;

  const sichtbar = useMemo(() => {
    const gefiltert = filterAnwenden(sucheAufgaben(quelle, sucheVerzoegert), bedingungen, felder);
    return sortiereAufgaben(gefiltert, sortierung);
  }, [quelle, sucheVerzoegert, bedingungen, felder, sortierung]);

  // Erledigte nach Fälligkeit zu gruppieren ("Überfällig") wäre irreführend.
  const wirksameGruppierung: Gruppierung = segment === "erledigt" && gruppierung === "faelligkeit" ? "keine" : gruppierung;
  const gruppen = useMemo(() => gruppiereAufgaben(sichtbar, wirksameGruppierung), [sichtbar, wirksameGruppierung]);

  const zahlen = useMemo(() => kennzahlen(offenQuery.data ?? [], heuteIso()), [offenQuery.data]);

  const [eingeklapptAlle, setEingeklapptAlle] = useState<Partial<Record<Gruppierung, string[]>>>({});
  const eingeklappt = eingeklapptAlle[wirksameGruppierung] ?? eingeklapptLesen(wirksameGruppierung);
  const setEingeklappt = (keys: string[]) => {
    eingeklapptSchreiben(wirksameGruppierung, keys);
    setEingeklapptAlle((alt) => ({ ...alt, [wirksameGruppierung]: keys }));
  };
  const gruppeUmschalten = (key: string) =>
    setEingeklappt(eingeklappt.includes(key) ? eingeklappt.filter((k) => k !== key) : [...eingeklappt, key]);
  const alleEinklappen = () => setEingeklappt(gruppen.map((g) => g.key));
  const alleAusklappen = () => setEingeklappt([]);
  const alleEingeklappt = gruppen.length > 0 && gruppen.every((g) => eingeklappt.includes(g.key));

  const invalidieren = () => queryClient.invalidateQueries({ queryKey: ["projekt-aufgaben"] });
  const umschalten = useMutation({
    mutationFn: ({ id, erledigt }: { id: string; erledigt: boolean; still?: boolean }) => projektAufgabenApi.update(id, { erledigt }),
    onSuccess: (_, v) => {
      if (v.erledigt) {
        toast.erfolg("Aufgabe erledigt", { label: "Rückgängig", onClick: () => umschalten.mutate({ id: v.id, erledigt: false, still: true }) });
      } else if (!v.still) {
        toast.erfolg("Aufgabe wieder offen");
      }
      void invalidieren();
    },
  });

  // Gruppierung und Sortierung gehören zur Ansicht ("Kita diese Woche, nach Projekt"), nicht nur zum Filter.
  const ansichtenZusatz = {
    lesen: () => ({ gruppe: gruppierung, sort: sortierung }),
    anwenden: (zusatz: Record<string, unknown>) => {
      setGruppierung(gruppierungAusUrl(typeof zusatz.gruppe === "string" ? zusatz.gruppe : null));
      setSortierung(sortierungAusUrl(typeof zusatz.sort === "string" ? zusatz.sort : null));
    },
  };

  return {
    ansichtenZusatz,
    segment,
    setSegment,
    gruppierung,
    wirksameGruppierung,
    setGruppierung,
    sortierung,
    setSortierung,
    felder,
    zustand,
    sichtbar,
    gruppen,
    zahlen,
    anzahlErledigt: erledigtQuery.data?.length ?? null,
    laedt: aktiv.isLoading,
    fehler: aktiv.error,
    hatDaten: !!aktiv.data,
    neuLaden: () => void aktiv.refetch(),
    eingeklappt,
    gruppeUmschalten,
    alleEinklappen,
    alleAusklappen,
    alleEingeklappt,
    umschalten: (a: ProjektAufgabe) => umschalten.mutate({ id: a.id, erledigt: !a.erledigt_am }),
    invalidieren,
  };
}

export type MeineAufgabenZustand = ReturnType<typeof useMeineAufgaben>;
