import { useQuery } from "@tanstack/react-query";
import { Box, Building2, CalendarClock, CircleDot, Folder, Receipt, Tag as TagIcon, UserRound, Wrench } from "lucide-react";
import { useCallback, useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { anlagenApi, kundenApi, projekteApi, tagsApi } from "../api/endpoints";
import { useFilterZustand, type FilterZustand } from "../components/filter/useFilterZustand";
import type { FilterBedingung, FilterFeld } from "../components/filter/typen";
import { bedingungenAusUrl, bedingungenZuJson } from "../components/filter/url";
import {
  ABRECHNUNGSART_OPTIONEN,
  ALTE_SCHLUESSEL,
  LEISTUNGSTYP_OPTIONEN,
  PERSON_ICH,
  SORTIERUNGEN,
  STATUS_OPTIONEN,
  alteVorlageUmrechnen,
  bedingungenZuParameter,
} from "../config/vorgaengeFilter";
import { useAuth } from "../context/AuthContext";
import type { FeedCard } from "../types";

const STANDARD_SORTIERUNG = SORTIERUNGEN[0].wert;
// Spiegelt die Router-Abhängigkeit von /api/tags -- andere Rollen bekämen nur ein 403.
const ROLLEN_MIT_TAGLISTE = ["mandant_admin", "custom", "loesch_operativ"];

/** Filterzustand, Felder und Server-Parameter für Feed (Feld) und Vorgangsliste (Office). */
export function useVorgaengeFilter(): {
  felder: FilterFeld<FeedCard>[];
  zustand: FilterZustand;
  /** Ohne Standard-Einschränkung des Feeds (offene Status) -- die ergänzt die Seite selbst. */
  parameter: Record<string, string>;
  hatStatusBedingung: boolean;
  sortierung: string;
  setSortierung(s: string): void;
} {
  const { currentUser, hatRecht } = useAuth();
  const [params, setParams] = useSearchParams();

  const fRoh = params.get("f");
  const kundeId = useMemo(() => {
    const b = bedingungenAusUrl(fRoh).find((x) => x.feld === "kunde" && x.op === "ist");
    return Array.isArray(b?.wert) ? b.wert[0] : typeof b?.wert === "string" ? b.wert : undefined;
  }, [fRoh]);

  const darfKunden = hatRecht("kunden", "sehen");
  const darfProjekte = hatRecht("projekte", "sehen");
  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list(), enabled: darfKunden });
  const { data: projekte } = useQuery({ queryKey: ["projekte"], queryFn: () => projekteApi.list(), enabled: darfProjekte });
  // Wie bisher erst ab gewähltem Kunden laden: eine Anlagenliste über den ganzen Mandanten wäre für einen Filter zu groß.
  const { data: anlagen } = useQuery({
    queryKey: ["anlagen", kundeId],
    queryFn: () => anlagenApi.list(kundeId),
    enabled: !!kundeId,
  });
  const { data: tags } = useQuery({
    queryKey: ["tags"],
    queryFn: () => tagsApi.list(),
    enabled: !!currentUser && ROLLEN_MIT_TAGLISTE.includes(currentUser.role) && hatRecht("vorgaenge", "sehen"),
    retry: false,
  });

  const felder = useMemo<FilterFeld<FeedCard>[]>(() => {
    const liste: FilterFeld<FeedCard>[] = [
      { key: "status", label: "Status", typ: "auswahl", icon: CircleDot, optionen: STATUS_OPTIONEN, operatoren: ["ist", "ist_nicht"] },
    ];
    if (darfKunden) {
      liste.push({
        key: "kunde",
        label: "Kunde",
        typ: "verknuepfung",
        icon: Building2,
        optionen: (kunden ?? []).map((k) => ({ wert: k.id, label: k.name })),
        operatoren: ["ist"],
        einzelwert: true,
      });
      if (kundeId) {
        liste.push({
          key: "anlage",
          label: "Anlage",
          typ: "verknuepfung",
          icon: Box,
          optionen: (anlagen ?? []).map((a) => ({ wert: a.id, label: a.bezeichnung })),
          operatoren: ["ist"],
          einzelwert: true,
        });
      }
    }
    if (darfProjekte) {
      liste.push({
        key: "projekt",
        label: "Projekt",
        typ: "verknuepfung",
        icon: Folder,
        optionen: (projekte ?? []).map((p) => ({ wert: p.id, label: p.name })),
        operatoren: ["ist"],
        einzelwert: true,
      });
    }
    liste.push(
      { key: "leistungstyp", label: "Leistungstyp", typ: "auswahl", icon: Wrench, optionen: LEISTUNGSTYP_OPTIONEN, operatoren: ["ist"], einzelwert: true },
      { key: "abrechnungsart", label: "Abrechnungsart", typ: "auswahl", icon: Receipt, optionen: ABRECHNUNGSART_OPTIONEN, operatoren: ["ist"], einzelwert: true },
      { key: "faellig", label: "Fällig", typ: "datum", icon: CalendarClock, operatoren: ["vor", "nach", "am", "zwischen", "relativ"] },
    );
    const tagLabels = (tags ?? []).map((t) => t.label);
    // Ohne Tag-Liste (fehlendes Recht, noch nicht geladen) bleibt ein Textwert statt eines leeren Auswahlfelds.
    liste.push(
      tagLabels.length > 0
        ? {
            key: "tag",
            label: "Tag",
            typ: "liste",
            icon: TagIcon,
            optionen: tagLabels.map((l) => ({ wert: l, label: `#${l}` })),
            operatoren: ["enthaelt"],
            einzelwert: true,
          }
        : { key: "tag", label: "Tag", typ: "text", icon: TagIcon, operatoren: ["enthaelt"] },
      {
        key: "zugewiesen",
        label: "Zugewiesen an",
        typ: "person",
        icon: UserRound,
        optionen: [{ wert: PERSON_ICH, label: "Ich" }],
        operatoren: ["ist"],
        einzelwert: true,
      },
    );
    return liste;
  }, [darfKunden, darfProjekte, kunden, projekte, anlagen, tags, kundeId]);

  const zustand = useFilterZustand({ felder });

  // Alte Links (`/feed?faellig_von=…`, `?projekt_id=…`) einmalig in `f` umrechnen.
  useEffect(() => {
    if (!ALTE_SCHLUESSEL.some((k) => params.has(k))) return;
    setParams(
      (prev) => {
        const n = new URLSearchParams(prev);
        const alt: Record<string, string> = {};
        for (const k of ALTE_SCHLUESSEL) {
          const v = n.get(k);
          if (v) alt[k] = v;
          n.delete(k);
        }
        const neu: FilterBedingung[] = [...bedingungenAusUrl(n.get("f")), ...alteVorlageUmrechnen(alt)];
        if (neu.length > 0) n.set("f", bedingungenZuJson(neu));
        return n;
      },
      { replace: true },
    );
  }, [params, setParams]);

  const sortRoh = params.get("sort");
  const sortierung = SORTIERUNGEN.some((s) => s.wert === sortRoh) ? (sortRoh as string) : STANDARD_SORTIERUNG;
  const setSortierung = useCallback(
    (s: string) =>
      setParams(
        (prev) => {
          const n = new URLSearchParams(prev);
          if (s === STANDARD_SORTIERUNG) n.delete("sort");
          else n.set("sort", s);
          return n;
        },
        { replace: true },
      ),
    [setParams],
  );

  const suche = zustand.sucheVerzoegert.trim();
  const parameter = useMemo(
    () => ({
      ...bedingungenZuParameter(zustand.bedingungen),
      ...(suche ? { q: suche } : {}),
      ...(sortierung !== STANDARD_SORTIERUNG ? { sort: sortierung } : {}),
    }),
    [zustand.bedingungen, suche, sortierung],
  );

  return {
    felder,
    zustand,
    parameter,
    hatStatusBedingung: zustand.bedingungen.some((b) => b.feld === "status"),
    sortierung,
    setSortierung,
  };
}
