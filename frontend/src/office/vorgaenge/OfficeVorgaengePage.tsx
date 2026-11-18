import { Columns3, Inbox, LayoutGrid, List, Plus, Rss } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { FilterLeiste } from "../../components/filter/FilterLeiste";
import { SkeletonList } from "../../components/Skeleton";
import { VorgaengeSortierMenue } from "../../components/VorgaengeSortierMenue";
import { alteVorlageUmrechnen } from "../../config/vorgaengeFilter";
import { useAlleSeitenLaden, useVorgangsListe } from "../../hooks/useVorgangsListe";
import { useVorgaengeFilter } from "../../hooks/useVorgaengeFilter";
import type { FeedCard } from "../../types";
import { AnsichtUmschalter, SeitenKopf } from "../OfficeUi";
import { VorgaengeKanban } from "./VorgaengeKanban";
import { VorgaengeListe } from "./VorgaengeListe";
import { VorgaengeRaster } from "./VorgaengeRaster";
import { VorgaengeTabelle } from "./VorgaengeTabelle";

type Ansicht = "liste" | "kanban" | "raster" | "tabelle";

const ANSICHT_KEY = "fieldvibe-office-vorgaenge-ansicht";

const UMSCHALTER = [
  { wert: "liste" as const, label: "Feed", icon: Rss },
  { wert: "kanban" as const, label: "Kanban", icon: Columns3 },
  { wert: "raster" as const, label: "Raster", icon: LayoutGrid },
  { wert: "tabelle" as const, label: "Liste", icon: List },
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

/** Filterzeile mit Bedingungen und Suche (beides serverseitig über `GET /api/feed`); die Sortierung bleibt ein
 * eigenes Menü neben dem Ansicht-Umschalter. */
export function OfficeVorgaengePage() {
  const navigate = useNavigate();
  const [ansicht, setAnsicht] = useState<Ansicht>(gespeicherteAnsicht);
  const { felder, zustand, parameter, sortierung, setSortierung } = useVorgaengeFilter();

  const wechsleAnsicht = (neu: Ansicht) => {
    setAnsicht(neu);
    try {
      localStorage.setItem(ANSICHT_KEY, neu);
    } catch {
      // privater Modus -- die Auswahl gilt dann nur für diese Sitzung
    }
  };

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading, error: ladeFehler, refetch: neuLaden } =
    useVorgangsListe(parameter);

  // Kanban und Raster zeigen alle Treffer nebeneinander -- eine seitenweise
  // nachgeladene Liste haette dort Luecken in einzelnen Spalten.
  useAlleSeitenLaden(ansicht !== "liste", hasNextPage, fetchNextPage);

  const vorgaenge: FeedCard[] = data?.pages.flatMap((p) => p.items) ?? [];
  const suchtext = zustand.sucheVerzoegert.trim();

  return (
    <div>
      <SeitenKopf titel="Vorgänge" anzahl={vorgaenge.length}>
        <AnsichtUmschalter wert={ansicht} optionen={UMSCHALTER} onWechsel={wechsleAnsicht} />
        <VorgaengeSortierMenue wert={sortierung} onWechsel={setSortierung} />
        <button onClick={() => navigate("/neu")} className="btn-ap-primary">
          <Plus size={14} strokeWidth={2.5} aria-hidden="true" />
          Neuer Vorgang
        </button>
      </SeitenKopf>

      <FilterLeiste
        felder={felder}
        zustand={zustand}
        suchPlatzhalter="Vorgang, Kunde, Anlage…"
        ansichten="vorgaenge"
        alteVorlageUmrechnen={alteVorlageUmrechnen}
        variante="office"
        className="mb-4"
      />

      {isLoading ? (
        <SkeletonList count={4} />
      ) : ladeFehler && !data ? (
        <FehlerZustand fehler={ladeFehler} was="Die Vorgänge" onErneut={() => void neuLaden()} />
      ) : vorgaenge.length === 0 ? (
        <EmptyState
          icon={Inbox}
          text={
            suchtext
              ? `Nichts gefunden für ‚${suchtext}‘`
              : zustand.aktiveAnzahl > 0
                ? "Keine Treffer für diese Filter"
                : "Keine Vorgänge gefunden."
          }
          action={
            (suchtext || zustand.aktiveAnzahl > 0) && (
              <button onClick={zustand.zuruecksetzen} className="btn-ap mt-1 text-sekundaer">
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
