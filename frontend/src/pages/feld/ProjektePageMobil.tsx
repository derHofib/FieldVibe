import { useQuery } from "@tanstack/react-query";
import { CalendarRange, Folder } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { projekteApi, zeitplanApi } from "../../api/endpoints";
import { AbschnittskopfA } from "../../components/apple/AbschnittsKopf";
import { GroupedList, GroupedListRow } from "../../components/apple/GroupedList";
import { SymbolKachel } from "../../components/apple/SymbolKachel";
import { useAuth } from "../../context/AuthContext";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import { formatKurz, parseTag } from "../../office/projekte/zeitplan/zeitplanLogik";

/** Mobile Projektliste (Abschnitt 5, "Projekte"-Tab): das bestehende
 * Kanban-Board (office/OfficeProjektePage.tsx) ist fuer die Desktop-Breite
 * mit Drag&Drop gebaut, nicht fuer die schmale Feld-App-Spalte -- deshalb
 * hier eine eigene, einfache gruppierte Liste. Tippen auf ein Projekt
 * filtert den Feed (Aufträge-Tab) auf dessen Vorgaenge. */
export function ProjektePageMobil() {
  const { hatRecht } = useAuth();
  // Techniker haben meist nur "Zeitplan ansehen" (projekte.zeitplan_sehen), nicht
  // projekte.sehen -- dann gibt es statt der Projektliste "Meine Zeitpläne".
  if (!hatRecht("projekte", "sehen") && hatRecht("projekte", "zeitplan_sehen")) return <MeineZeitplaeneMobil />;
  return <ProjektListeMobil />;
}

/** Feld-App-Einstieg fuer Nutzer ohne projekte.sehen: Projekte, in denen sie mitarbeiten. */
function MeineZeitplaeneMobil() {
  const navigate = useNavigate();
  const { data: projekte, isLoading } = useQuery({
    queryKey: ["meine-zeitplaene"],
    queryFn: zeitplanApi.meine,
  });
  const liste = projekte ?? [];

  return (
    <div className="-mx-3 -mt-4 pb-8">
      <AbschnittskopfA titel="Meine Zeitpläne" anzahl={liste.length} />
      <div className="px-4">
        {isLoading ? (
          <SkeletonList count={4} />
        ) : liste.length === 0 ? (
          <EmptyState icon={CalendarRange} text="Aktuell bist du in keinem Projekt eingeplant." />
        ) : (
          <GroupedList>
            {liste.map((projekt, i) => (
              <GroupedListRow
                key={projekt.id}
                onClick={() => navigate(`/projekte/${projekt.id}/zeitplan`)}
                navigierbar
                last={i === liste.length - 1}
                minHoehe={56}
              >
                <SymbolKachel icon={CalendarRange} farbe="orange" />
                <div className="min-w-0">
                  <p className="truncate text-[17px] text-label">{projekt.name}</p>
                  <p className="flex text-[13px] text-label2">
                    {projekt.naechster_schritt_titel ? (
                      <>
                        <span className="truncate">Nächster Schritt: {projekt.naechster_schritt_titel}</span>
                        {projekt.naechster_schritt_start && (
                          <span className="shrink-0 whitespace-pre"> · {formatKurz(parseTag(projekt.naechster_schritt_start))}</span>
                        )}
                      </>
                    ) : (
                      "Kein anstehender Schritt"
                    )}
                  </p>
                </div>
              </GroupedListRow>
            ))}
          </GroupedList>
        )}
      </div>
    </div>
  );
}

function ProjektListeMobil() {
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
