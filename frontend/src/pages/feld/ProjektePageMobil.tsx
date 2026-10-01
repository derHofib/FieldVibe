import { useQuery } from "@tanstack/react-query";
import { CalendarRange, Folder } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { projekteApi } from "../../api/endpoints";
import { AbschnittskopfA } from "../../components/apple/AbschnittsKopf";
import { GroupedList, GroupedListRow } from "../../components/apple/GroupedList";
import { SymbolKachel } from "../../components/apple/SymbolKachel";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";

/** Mobile Projektliste (Abschnitt 5, "Projekte"-Tab): das bestehende
 * Kanban-Board (office/OfficeProjektePage.tsx) ist fuer die Desktop-Breite
 * mit Drag&Drop gebaut, nicht fuer die schmale Feld-App-Spalte -- deshalb
 * hier eine eigene, einfache gruppierte Liste. Tippen auf ein Projekt
 * filtert den Feed (Aufträge-Tab) auf dessen Vorgaenge. */
export function ProjektePageMobil() {
  const navigate = useNavigate();
  const { data: projekte, isLoading } = useQuery({
    queryKey: ["projekte"],
    queryFn: () => projekteApi.list(),
  });

  const aktive = (projekte ?? []).filter((p) => !p.archiviert);

  return (
    // -mx-3 -mt-4 hebt das Aussenpolster von FeldLayout.tsx auf, siehe
    // gleiche Begruendung in MehrPage.tsx.
    <div className="-mx-3 -mt-4 pb-8">
      <AbschnittskopfA titel="Projekte" anzahl={aktive.length} />

      <div className="px-4">
        {isLoading ? (
          <SkeletonList count={4} />
        ) : aktive.length === 0 ? (
          <EmptyState icon={Folder} text="Keine aktiven Projekte. Neue Projekte werden im Büro angelegt." />
        ) : (
          <GroupedList>
            {aktive.map((projekt, i) => (
              // Zeitplan-Knopf als Geschwister ueber der Zeile (nicht darin): ein
              // Button im Button waere ungueltiges HTML.
              <div key={projekt.id} className="relative">
                <GroupedListRow
                  onClick={() => navigate(`/feed?projekt_id=${projekt.id}`)}
                  navigierbar
                  last={i === aktive.length - 1}
                >
                  <SymbolKachel icon={Folder} farbe="indigo" />
                  <div className="min-w-0 pr-9">
                    <p className="truncate text-[17px] text-label">{projekt.name}</p>
                    {projekt.beschreibung && (
                      <p className="truncate text-[13px] text-label2">{projekt.beschreibung}</p>
                    )}
                  </div>
                </GroupedListRow>
                <button
                  type="button"
                  onClick={() => navigate(`/projekte/${projekt.id}/zeitplan`)}
                  aria-label={`Zeitplan von ${projekt.name}`}
                  className="btn-touch absolute top-1/2 right-8 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full text-tint hover:bg-fill"
                >
                  <CalendarRange size={20} strokeWidth={1.5} aria-hidden="true" />
                </button>
              </div>
            ))}
          </GroupedList>
        )}
      </div>
    </div>
  );
}
