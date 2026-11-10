import { useQuery } from "@tanstack/react-query";
import { ClipboardList } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { partnerPortalApi } from "../api/endpoints";
import { AbschnittskopfB } from "../components/apple/AbschnittsKopf";
import { GroupedList, GroupedListRow } from "../components/apple/GroupedList";
import { StatusPille } from "../components/apple/StatusPille";
import { EmptyState } from "../components/EmptyState";
import { SkeletonList } from "../components/Skeleton";
import type { PartnerVorgang } from "../types";
import { auftragsPhase, auftragsPille, type AuftragsPhase } from "./partnerStatus";

const GRUPPEN: { phase: AuftragsPhase; titel: string }[] = [
  { phase: "entscheiden", titel: "Zur Entscheidung" },
  { phase: "aktiv", titel: "Aktiv" },
  { phase: "beendet", titel: "Abgeschlossen & abgelehnt" },
];

export function PartnerAuftraegePage() {
  const navigate = useNavigate();
  const { data, isLoading, error } = useQuery({
    queryKey: ["partnerportal-auftraege"],
    queryFn: partnerPortalApi.auftraege,
  });

  const nachPhase = new Map<AuftragsPhase, PartnerVorgang[]>();
  for (const a of data ?? []) nachPhase.set(auftragsPhase(a), [...(nachPhase.get(auftragsPhase(a)) ?? []), a]);

  return (
    <main className="mx-auto max-w-2xl px-3 py-4 pb-10">
      <h1 className="ap-heading px-5 pt-2 pb-1 text-[26px] font-bold text-label">Aufträge</h1>
      <p className="px-5 text-[15px] text-label2">Ihnen zugewiesene Aufträge.</p>

      {isLoading ? (
        <div className="px-4 pt-4">
          <SkeletonList count={4} />
        </div>
      ) : error ? (
        <p role="alert" className="px-5 pt-4 text-sm text-st-fehlt">
          Die Aufträge konnten nicht geladen werden.
        </p>
      ) : (data ?? []).length === 0 ? (
        <div className="px-4 pt-4">
          <EmptyState icon={ClipboardList} text="Ihnen sind noch keine Aufträge zugewiesen." />
        </div>
      ) : (
        GRUPPEN.map(({ phase, titel }) => {
          const liste = nachPhase.get(phase);
          if (!liste?.length) return null;
          return (
            <section key={phase} aria-label={titel}>
              <AbschnittskopfB titel={titel} />
              <div className="px-4">
                <GroupedList>
                  {liste.map((a, i) => {
                    const pille = auftragsPille(a);
                    return (
                      <GroupedListRow
                        key={a.id}
                        navigierbar
                        minHoehe={64}
                        last={i === liste.length - 1}
                        onClick={() => navigate(`/partnerportal/auftraege/${a.id}`)}
                      >
                        <div className="min-w-0 flex-1">
                          <p className="line-clamp-2 text-[17px] leading-snug text-label">{a.titel}</p>
                          <p className="truncate text-[13px] text-label2">
                            {a.vorgangsnummer} · {a.kunde_name}
                          </p>
                        </div>
                        <div className="shrink-0">
                          <StatusPille status={pille.status} label={pille.label} />
                        </div>
                      </GroupedListRow>
                    );
                  })}
                </GroupedList>
              </div>
            </section>
          );
        })
      )}
    </main>
  );
}
