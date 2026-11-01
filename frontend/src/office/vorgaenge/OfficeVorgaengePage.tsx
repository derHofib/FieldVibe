import { useQuery } from "@tanstack/react-query";
import { Columns3, Filter, Inbox, LayoutGrid, List, Plus, Table2, X } from "lucide-react";
import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import { anlagenApi, kundenApi, projekteApi } from "../../api/endpoints";
import { FilterChip } from "../../components/apple/FilterChip";
import { SearchField } from "../../components/apple/SearchField";
import { vorgangStatusZuToken } from "../../components/apple/status";
import { EmptyState } from "../../components/EmptyState";
import { FilterVorlagenLeiste } from "../../components/FilterVorlagenLeiste";
import {
  LEISTUNGSTYP_LABEL,
  STATUS_LABEL,
  filterChipLabel,
} from "../../config/vorgangDarstellung";
import { useAlleSeitenLaden, useVorgangsListe } from "../../hooks/useVorgangsListe";
import type { FeedCard, VorgangStatus } from "../../types";
import { AnsichtUmschalter, SeitenKopf } from "../OfficeUi";
import { VorgaengeKanban } from "./VorgaengeKanban";
import { VorgaengeListe } from "./VorgaengeListe";
import { VorgaengeRaster } from "./VorgaengeRaster";
import { VorgaengeTabelle } from "./VorgaengeTabelle";

type Ansicht = "liste" | "kanban" | "raster" | "tabelle";

const ANSICHT_KEY = "fieldvibe-office-vorgaenge-ansicht";

const UMSCHALTER = [
  { wert: "liste" as const, label: "Liste", icon: List },
  { wert: "kanban" as const, label: "Kanban", icon: Columns3 },
  { wert: "raster" as const, label: "Raster", icon: LayoutGrid },
  { wert: "tabelle" as const, label: "Tabelle", icon: Table2 },
];

function gespeicherteAnsicht(): Ansicht {
  try {
    const wert = localStorage.getItem(ANSICHT_KEY);
    if (wert === "liste" || wert === "kanban" || wert === "raster" || wert === "tabelle") return wert;
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
  const { data: projekte } = useQuery({ queryKey: ["projekte"], queryFn: () => projekteApi.list() });
  // Wie beim Leistungsverzeichnis abhaengiger Picker: erst ab gewaehltem
  // Kunden laden, sonst waere die Liste ueber alle Mandanten-Anlagen hinweg
  // fuer einen reinen Filter unnoetig gross.
  const { data: anlagenFuerKunde } = useQuery({
    queryKey: ["anlagen", filter.kunde_id],
    queryFn: () => anlagenApi.list(filter.kunde_id),
    enabled: !!filter.kunde_id,
  });

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
    .map(([key, value]) => ({ key, label: filterChipLabel(key, value, kunden, projekte) }));

  return (
    <div>
      <SeitenKopf titel="Vorgänge" anzahl={vorgaenge.length}>
        <AnsichtUmschalter wert={ansicht} optionen={UMSCHALTER} onWechsel={wechsleAnsicht} />
        <SearchField value={suche} onChange={setSuche} placeholder="Vorgang, Kunde, Anlage…" className="w-56" />
        <button onClick={() => navigate("/neu")} className="btn-ap-primary">
          <Plus size={14} strokeWidth={2.5} aria-hidden="true" />
          Neuer Vorgang
        </button>
      </SeitenKopf>

      <div className="mb-2 flex flex-wrap items-center gap-2">
        <FilterChip
          label="Überfällig"
          aktiv={filter.faellig_bis === heuteIso() && !filter.faellig_von}
          onClick={() => setField("faellig_bis", filter.faellig_bis === heuteIso() ? "" : heuteIso())}
        />
        <FilterChip
          label="Diese Woche fällig"
          aktiv={filter.faellig_bis === heuteIso(7)}
          onClick={() => setField("faellig_bis", filter.faellig_bis === heuteIso(7) ? "" : heuteIso(7))}
        />
        <button
          onClick={() => setZeigeFilter((v) => !v)}
          aria-pressed={zeigeFilter || aktiveFilterAnzahl > 0}
          className={`inline-flex h-[26px] items-center gap-1.5 rounded-[13px] px-2.5 text-xs font-medium ${
            zeigeFilter || aktiveFilterAnzahl > 0 ? "bg-tint-solid text-white" : "bg-fill text-label"
          }`}
        >
          <Filter size={13} strokeWidth={2} aria-hidden="true" />
          Weitere Filter
          {aktiveFilterAnzahl > 0 && (
            <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-white/25 px-1 text-[10px] font-bold">
              {aktiveFilterAnzahl}
            </span>
          )}
        </button>
      </div>

      {filterChips.length > 0 && !zeigeFilter && (
        <div className="card-ap mb-4 flex flex-wrap items-center gap-1.5 p-2.5">
          {filterChips.map((c) => (
            <span
              key={c.key}
              className="flex items-center gap-1.5 rounded-[13px] bg-fill py-1 pr-1.5 pl-2.5 text-xs font-medium text-label"
            >
              {c.label}
              <button
                onClick={() => setField(c.key, "")}
                aria-label={`${c.label} entfernen`}
                className="flex h-4 w-4 items-center justify-center rounded-full bg-fill2 text-label2"
              >
                <X size={9} strokeWidth={3} />
              </button>
            </span>
          ))}
          <button onClick={() => setZeigeFilter(true)} className="ml-auto text-xs font-semibold text-tint">
            Bearbeiten
          </button>
        </div>
      )}

      {zeigeFilter && (
        <div className="card-ap mb-4 space-y-3 p-3">
          <div>
            <div className="mb-1 text-xs font-medium text-label2">
              Status (Mehrfachauswahl möglich)
            </div>
            <div className="flex flex-wrap gap-1.5">
              {(Object.keys(STATUS_LABEL) as VorgangStatus[]).map((value) => (
                <FilterChip
                  key={value}
                  label={STATUS_LABEL[value]}
                  status={vorgangStatusZuToken(value)}
                  aktiv={aktiveStatus.includes(value)}
                  onClick={() => toggleStatus(value)}
                />
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-6">
            <select
              value={filter.kunde_id ?? ""}
              onChange={(e) => setField("kunde_id", e.target.value)}
              className="field-ap"
            >
              <option value="">Alle Kunden</option>
              {(kunden ?? []).map((k) => (
                <option key={k.id} value={k.id}>
                  {k.name}
                </option>
              ))}
            </select>
            <select
              value={filter.anlage_id ?? ""}
              onChange={(e) => setField("anlage_id", e.target.value)}
              disabled={!filter.kunde_id}
              className="field-ap disabled:opacity-50"
            >
              <option value="">{filter.kunde_id ? "Alle Anlagen" : "Erst Kunden wählen"}</option>
              {(anlagenFuerKunde ?? []).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.bezeichnung}
                </option>
              ))}
            </select>
            <select
              value={filter.projekt_id ?? ""}
              onChange={(e) => setField("projekt_id", e.target.value)}
              className="field-ap"
            >
              <option value="">Alle Projekte</option>
              {(projekte ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <select
              value={filter.leistungstyp ?? ""}
              onChange={(e) => setField("leistungstyp", e.target.value)}
              className="field-ap"
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
              className="field-ap"
            />
            <input
              type="date"
              value={filter.faellig_bis ?? ""}
              onChange={(e) => setField("faellig_bis", e.target.value)}
              title="Fällig bis"
              className="field-ap"
            />
            <input
              value={filter.tag ?? ""}
              onChange={(e) => setField("tag", e.target.value)}
              placeholder="#Tag"
              className="field-ap"
            />
            <select
              value={filter.sort ?? "last_activity_at"}
              onChange={(e) => setField("sort", e.target.value)}
              className="field-ap"
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
        <p className="py-10 text-center text-sm text-label2">Lädt…</p>
      ) : vorgaenge.length === 0 ? (
        <EmptyState
          icon={Inbox}
          text={aktiveFilterAnzahl > 0 ? "Keine Vorgänge für die aktuellen Filter." : "Keine Vorgänge gefunden."}
          action={
            aktiveFilterAnzahl > 0 && (
              <button onClick={() => setFilter(LEER_FILTER)} className="btn-ap mt-1 text-xs">
                Filter zurücksetzen
              </button>
            )
          }
        />
      ) : ansicht === "liste" ? (
        <VorgaengeListe
          vorgaenge={vorgaenge}
          hasNextPage={hasNextPage}
          isFetchingNextPage={isFetchingNextPage}
          onMehr={() => fetchNextPage()}
        />
      ) : ansicht === "kanban" ? (
        <VorgaengeKanban vorgaenge={vorgaenge} />
      ) : ansicht === "tabelle" ? (
        <VorgaengeTabelle vorgaenge={vorgaenge} />
      ) : (
        <VorgaengeRaster vorgaenge={vorgaenge} />
      )}
    </div>
  );
}
