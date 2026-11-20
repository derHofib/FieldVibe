import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";

import { kundenApi } from "../../api/endpoints";
import type { KundeRefKurz } from "../../types";
import { GroupedList, GroupedListRow } from "../apple/GroupedList";

/** Beziehung Hausverwaltung/WEG im Kundenprofil: "Verwaltet von …" bzw. Liste der verwalteten Kunden. */
export function KundeVerwaltung({ kundeId, verwaltetVon }: { kundeId: string; verwaltetVon: KundeRefKurz | null | undefined }) {
  const { data: verwaltete } = useQuery({
    queryKey: ["kunden", "verwaltete", kundeId],
    queryFn: () => kundenApi.verwaltete(kundeId),
    retry: false,
  });
  const liste = verwaltete ?? [];
  if (!verwaltetVon && liste.length === 0) return null;

  return (
    <>
      {verwaltetVon && (
        <p className="text-fliess text-label2">
          Verwaltet von{" "}
          <Link to={`/kunden/${verwaltetVon.id}`} className="font-medium text-tint-text hover:underline">
            {verwaltetVon.name}
          </Link>
        </p>
      )}
      {liste.length > 0 && (
        <section aria-label="Verwaltete Kunden">
          <h2 className="mb-2 text-fliess font-semibold text-label2">Verwaltete Kunden</h2>
          <GroupedList>
            {liste.map((k, i) => (
              <GroupedListRow key={k.id} last={i === liste.length - 1}>
                <Link to={`/kunden/${k.id}`} className="flex min-w-0 flex-1 items-center gap-2">
                  <span className="min-w-0 flex-1 truncate text-zeile text-label">{k.name}</span>
                  <ChevronRight size={16} strokeWidth={2} className="shrink-0 text-label3" aria-hidden="true" />
                </Link>
              </GroupedListRow>
            ))}
          </GroupedList>
        </section>
      )}
    </>
  );
}
