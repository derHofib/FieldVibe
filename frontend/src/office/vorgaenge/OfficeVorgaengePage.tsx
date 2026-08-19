import { useQuery } from "@tanstack/react-query";
import { Columns3, Filter, Inbox, LayoutGrid, List, Plus, Search, X } from "lucide-react";
import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import { kundenApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { FilterVorlagenLeiste } from "../../components/FilterVorlagenLeiste";
import {
  LEISTUNGSTYP_LABEL,
  STATUS_LABEL,
  filterChipLabel,
} from "../../config/vorgangDarstellung";
import { useAlleSeitenLaden, useVorgangsListe } from "../../hooks/useVorgangsListe";
import type { FeedCard } from "../../types";
import { AnsichtUmschalter, SeitenKopf } from "../OfficeUi";
import { VorgaengeKanban } from "./VorgaengeKanban";
import { VorgaengeListe } from "./VorgaengeListe";
import { VorgaengeRaster } from "./VorgaengeRaster";

type Ansicht = "liste" | "kanban" | "raster";

const ANSICHT_KEY = "fieldvibe-office-vorgaenge-ansicht";

const UMSCHALTER = [
  { wert: "liste" as const, label: "Liste", icon: List },
  { wert: "kanban" as const, label: "Kanban", icon: Columns3 },
  { wert: "raster" as const, label: "Raster", icon: LayoutGrid },
];

function gespeicherteAnsicht(): Ansicht {
  try {
    const wert = localStorage.getItem(ANSICHT_KEY);
    if (wert === "liste" || wert === "kanban" || wert === "raster") return wert;
  } catch {
    // privater Modus -- dann eben jedes Mal die Standardansicht
  }
  return "liste";
}

function heuteIso(offsetTage = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetTage);
  return d.toISOString().slice(0, 10);
}

const LEER_FILTER: Record<string, string> = {};

/** Dieselbe Filterleiste wie im Feed der Feld-App (Status-Mehrfachauswahl,
 * Kunde/Leistungstyp/Zeitraum/Tag/Sortierung, gespeicherte Filter) --
 * abweichend vom mobilen "Pill im Toolbar"-Muster (siehe FeedPage.tsx)
 * bleibt der Ausloeser hier ein Button mit Textlabel statt reinem Icon: am
 * Schreibtisch gibt es genug Platz, ein Verstecken hinter einem Icon loest
 * kein Platzproblem wie auf dem Handy. */
export function OfficeVorgaengePage() {
  const navigate = useNavigate();
  const [ansicht, setAnsicht] = useState<Ansicht>(gespeicherteAnsicht);
  const [suche, setSuche] = useState("");
  const [filter, setFilter] = useState<Record<string, string>>(LEER_FILTER);
  const [zeigeFilter, setZeigeFilter] = useState(false);

  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list() });

  const wechsleAnsicht = (neu: Ansicht) => {
    setAnsicht(neu);
    try {
      localStorage.setItem(ANSICHT_KEY, neu);
    } catch {
      // siehe oben -- die Auswahl gilt dann nur fuer diese Sitzung
    }
  };

  function setField(key: string, value: string) {
    setFilter((f) => {
      const next = { ...f };
      if (value) next[key] = value;
      else delete next[key];
      return next;
    });
  }

  const aktiveStatus = (filter.status ?? "").split(",").filter(Boolean);
  function toggleStatus(status: string) {
    const set = new Set(aktiveStatus);
    if (set.has(status)) set.delete(status);
    else set.add(status);
    setField("status", Array.from(set).join(","));
  }

  const anwendenFilter = useCallback((neu: Record<string, string>) => setFilter(neu), []);

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading } =
    useVorgangsListe(filter);

  // Kanban und Raster zeigen alle Treffer nebeneinander -- eine seitenweise
  // nachgeladene Liste haette dort Luecken in einzelnen Spalten.
  useAlleSeitenLaden(ansicht !== "liste", hasNextPage, fetchNextPage);

  const alle: FeedCard[] = data?.pages.flatMap((p) => p.items) ?? [];
  const suchbegriff = suche.trim().toLowerCase();
  const vorgaenge = suchbegriff
    ? alle.filter((v) =>
        [v.vorgangsnummer, v.titel, v.kunde_name, v.anlage_bezeichnung ?? ""]
          .join(" ")
          .toLowerCase()
          .includes(suchbegriff),
      )
    : alle;

  const aktiveFilterAnzahl = Object.keys(filter).length;
  const filterChips = Object.entries(filter)
    .filter(([, value]) => value)
    .map(([key, value]) => ({ key, label: filterChipLabel(key, value, kunden) }));

  return (
    <div>
      <SeitenKopf titel="Vorgänge" anzahl={vorgaenge.length}>
        <AnsichtUmschalter wert={ansicht} optionen={UMSCHALTER} onWechsel={wechsleAnsicht} />
        <div className="relative">
          <Search
            size={13}
            strokeWidth={2}
            className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-slate-400 dark:text-stone-500"
          />
          <input
            value={suche}
            onChange={(e) => setSuche(e.target.value)}
            placeholder="Vorgang, Kunde, Anlage…"
            className="w-56 rounded-lg border border-slate-200 bg-slate-100 py-1.5 pr-2 pl-7 text-xs text-slate-700 placeholder:text-slate-400 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-200 dark:placeholder:text-stone-500"
          />
        </div>
        <button
          onClick={() => navigate("/neu")}
          className="btn-clay flex items-center gap-1.5 rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-2 text-xs font-semibold text-white"
        >
          <Plus size={14} strokeWidth={2.5} />
          Neuer Vorgang
        </button>
      </SeitenKopf>

      <div className="mb-2 flex flex-wrap items-center gap-2">
        <button
          onClick={() => setField("faellig_bis", heuteIso())}
          className="rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-500 hover:text-slate-700 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-400 dark:hover:text-stone-200"
        >
          Überfällig
        </button>
        <button
          onClick={() => setField("faellig_bis", heuteIso(7))}
          className="rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-500 hover:text-slate-700 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-400 dark:hover:text-stone-200"
        >
          Diese Woche fällig
        </button>
        <button
          onClick={() => setZeigeFilter((v) => !v)}
          className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${
            zeigeFilter || aktiveFilterAnzahl > 0
              ? "btn-clay bg-linear-to-r from-cyan-500 to-blue-600 text-white"
              : "border border-slate-200 bg-slate-100 text-slate-500 hover:text-slate-700 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-400 dark:hover:text-stone-200"
          }`}
        >
          <Filter size={13} strokeWidth={2} />
          Weitere Filter
          {aktiveFilterAnzahl > 0 && (
            <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-white/25 px-1 text-[10px] font-bold">
              {aktiveFilterAnzahl}
            </span>
          )}
        </button>
      </div>

      {filterChips.length > 0 && !zeigeFilter && (
        <div className="mb-4 flex flex-wrap items-center gap-1.5 rounded-lg border border-slate-200 bg-white p-2.5 dark:border-stone-800 dark:bg-stone-900">
          {filterChips.map((c) => (
            <span
              key={c.key}
              className="flex items-center gap-1.5 rounded-full bg-slate-100 py-1 pr-1.5 pl-2.5 text-xs font-medium text-slate-700 dark:bg-stone-800 dark:text-stone-200"
            >
              {c.label}
              <button
                onClick={() => setField(c.key, "")}
                aria-label={`${c.label} entfernen`}
                className="flex h-4 w-4 items-center justify-center rounded-full bg-slate-200 text-slate-500 dark:bg-stone-700 dark:text-stone-400"
              >
                <X size={9} strokeWidth={3} />
              </button>
            </span>
          ))}
          <button
            onClick={() => setZeigeFilter(true)}
            className="ml-auto text-xs font-semibold text-blue-700 dark:text-blue-400"
          >
            Bearbeiten
          </button>
        </div>
      )}

      {zeigeFilter && (
        <div className="mb-4 space-y-3 rounded-lg border border-slate-200 bg-white p-3 dark:border-stone-800 dark:bg-stone-900">
          <div>
            <div className="mb-1 text-xs font-medium text-slate-500 dark:text-stone-400">
              Status (Mehrfachauswahl möglich)
            </div>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(STATUS_LABEL).map(([value, label]) => {
                const aktiv = aktiveStatus.includes(value);
                return (
                  <button
                    key={value}
                    type="button"
                    onClick={() => toggleStatus(value)}
                    className={`rounded-full px-3 py-1.5 text-xs font-medium ${
                      aktiv
                        ? "btn-clay bg-linear-to-r from-cyan-500 to-blue-600 text-white"
                        : "bg-slate-100 text-slate-600 dark:bg-stone-800 dark:text-stone-300"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-6">
            <select
              value={filter.kunde_id ?? ""}
              onChange={(e) => setField("kunde_id", e.target.value)}
              className="rounded-md border border-slate-300 bg-white px-2 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            >
              <option value="">Alle Kunden</option>
              {(kunden ?? []).map((k) => (
                <option key={k.id} value={k.id}>
                  {k.name}
                </option>
              ))}
            </select>
            <select
              value={filter.leistungstyp ?? ""}
              onChange={(e) => setField("leistungstyp", e.target.value)}
              className="rounded-md border border-slate-300 bg-white px-2 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            >
              <option value="">Alle Leistungstypen</option>
              {Object.entries(LEISTUNGSTYP_LABEL).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <input
              type="date"
              value={filter.faellig_von ?? ""}
              onChange={(e) => setField("faellig_von", e.target.value)}
              title="Fällig ab"
              className="rounded-md border border-slate-300 bg-white px-2 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
            <input
              type="date"
              value={filter.faellig_bis ?? ""}
              onChange={(e) => setField("faellig_bis", e.target.value)}
              title="Fällig bis"
              className="rounded-md border border-slate-300 bg-white px-2 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
            <input
              value={filter.tag ?? ""}
              onChange={(e) => setField("tag", e.target.value)}
              placeholder="#Tag"
              className="rounded-md border border-slate-300 bg-white px-2 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
            <select
              value={filter.sort ?? "last_activity_at"}
              onChange={(e) => setField("sort", e.target.value)}
              className="rounded-md border border-slate-300 bg-white px-2 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            >
              <option value="last_activity_at">Sortiert nach Aktivität</option>
              <option value="prioritaet">Sortiert nach Priorität</option>
            </select>
          </div>
        </div>
      )}

      <div className="mb-4">
        <FilterVorlagenLeiste entitaet="vorgaenge" filter={filter} onApply={anwendenFilter} />
      </div>

      {isLoading ? (
        <p className="py-10 text-center text-sm text-slate-400 dark:text-stone-500">Lädt…</p>
      ) : vorgaenge.length === 0 ? (
        <EmptyState icon={Inbox} text="Keine Vorgänge gefunden." />
      ) : ansicht === "liste" ? (
        <VorgaengeListe
          vorgaenge={vorgaenge}
          hasNextPage={hasNextPage}
          isFetchingNextPage={isFetchingNextPage}
          onMehr={() => fetchNextPage()}
        />
      ) : ansicht === "kanban" ? (
        <VorgaengeKanban vorgaenge={vorgaenge} />
      ) : (
        <VorgaengeRaster vorgaenge={vorgaenge} />
      )}
    </div>
  );
}
