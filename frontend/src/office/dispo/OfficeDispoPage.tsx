import { Inbox } from "lucide-react";

import { EmptyState } from "../../components/EmptyState";
import { useAlleSeitenLaden, useVorgangsListe } from "../../hooks/useVorgangsListe";
import type { FeedCard } from "../../types";
import { SeitenKopf } from "../OfficeUi";
import { VorgaengeKanban } from "../vorgaenge/VorgaengeKanban";

const DISPO_FILTER = { dispo: "true" };

/** Dispo als Kanban ueber alle offenen Vorgaenge. Teilt sich die
 * Spalten-Komponente mit der Vorgangs-Ansicht -- gleiche Karten, gleiche
 * Statusfarben, nur ein anderer Einstieg (hier ohne Ansicht-Umschalter, weil
 * Dispo genau diese eine Sicht braucht). */
export function OfficeDispoPage() {
  const { data, fetchNextPage, hasNextPage, isLoading } = useVorgangsListe(DISPO_FILTER);

  // Das Board zeigt alle Spalten nebeneinander -- ohne vollstaendiges
  // Nachladen fehlten in einzelnen Spalten Karten, die nur noch nicht
  // geladen sind. Dispo hat keinen Ansicht-Umschalter, also dauerhaft aktiv.
  useAlleSeitenLaden(true, hasNextPage, fetchNextPage);

  const vorgaenge: FeedCard[] = data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <div>
      <SeitenKopf titel="Dispo" anzahl={vorgaenge.length} />
      {isLoading ? (
        <p className="py-10 text-center text-sm text-slate-400 dark:text-stone-500">Lädt…</p>
      ) : vorgaenge.length === 0 ? (
        <EmptyState icon={Inbox} text="Keine Vorgänge zu disponieren." />
      ) : (
        <VorgaengeKanban vorgaenge={vorgaenge} />
      )}
    </div>
  );
}
