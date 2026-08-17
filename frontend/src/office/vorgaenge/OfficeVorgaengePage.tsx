import { Columns3, Inbox, LayoutGrid, List, Plus, Search } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { EmptyState } from "../../components/EmptyState";
import { useAlleSeitenLaden, useVorgangsListe } from "../../hooks/useVorgangsListe";
import type { FeedCard } from "../../types";
import { AnsichtUmschalter, FilterChip, SeitenKopf } from "../OfficeUi";
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

const SCHNELLFILTER = [
  { key: "alle", label: "Alle", params: {} as Record<string, string> },
  { key: "ueberfaellig", label: "Überfällig", params: { ueberfaellig: "true" } },
  { key: "wartet", label: "Wartet auf Kunde", params: { status: "wartet_kunde" } },
  { key: "woche", label: "Diese Woche fällig", params: { faellig_bis_tage: "7" } },
];

export function OfficeVorgaengePage() {
  const navigate = useNavigate();
  const [ansicht, setAnsicht] = useState<Ansicht>(gespeicherteAnsicht);
  const [schnellfilter, setSchnellfilter] = useState("alle");
  const [suche, setSuche] = useState("");

  const wechsleAnsicht = (neu: Ansicht) => {
    setAnsicht(neu);
    try {
      localStorage.setItem(ANSICHT_KEY, neu);
    } catch {
      // siehe oben -- die Auswahl gilt dann nur fuer diese Sitzung
    }
  };

  const filter = SCHNELLFILTER.find((f) => f.key === schnellfilter)?.params ?? {};

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

      <div className="mb-4 flex flex-wrap gap-2">
        {SCHNELLFILTER.map((f) => (
          <FilterChip
            key={f.key}
            label={f.label}
            aktiv={schnellfilter === f.key}
            onClick={() => setSchnellfilter(f.key)}
          />
        ))}
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
