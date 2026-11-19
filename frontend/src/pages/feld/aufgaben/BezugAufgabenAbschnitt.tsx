import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { projekteApi, projektAufgabenApi } from "../../../api/endpoints";
import { AbhakKreis } from "../../../components/apple/AbhakKreis";
import { useToast } from "../../../components/Toast";
import { istOfficeHost } from "../../../office/hostname";
import { ProjektAufgabeDetailPanel } from "../../../office/projekte/ProjektAufgabeDetailPanel";
import type { ProjektAufgabe } from "../../../types";
import { heuteIso } from "../../../utils/format";
import { ABSCHNITT_AKTION, Abschnitt } from "../vorgang/Abschnitt";
import { faelligText } from "./aufgabenLogik";

/** Abschnitt "Aufgaben" an einem Auftrag oder Vorgang (Rückverlinkung aus "Meine Aufgaben"). Ohne Aufgaben bleibt
 * nur der Link "+ Aufgabe" stehen; Sichtbarkeit (private Aufgaben nur für mich, Kanban-Karten mit Recht) regelt der
 * Server. Im Office öffnet ein Klick die Aufgabe als ganze Seite, in der Feld-App (keine Detailroute) das Panel. */
export function BezugAufgabenAbschnitt({ vorgangId, auftragId }: { vorgangId?: string; auftragId?: string }) {
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [panel, setPanel] = useState<ProjektAufgabe | null | undefined>(undefined);
  const bezug = vorgangId ? { vorgang_id: vorgangId } : { auftrag_id: auftragId };

  const { data } = useQuery({
    queryKey: ["projekt-aufgaben", "bezug", bezug],
    queryFn: () => projektAufgabenApi.list({ ...bezug, erledigt: "alle" }),
    enabled: !!(vorgangId || auftragId),
  });
  // Unteraufgaben gehören zur Karte der Eltern-Aufgabe und stehen hier nicht einzeln.
  const aufgaben = (data ?? []).filter((a) => !a.eltern_aufgabe_id);

  const { data: spalten } = useQuery({
    queryKey: ["projekt-spalten", panel?.projekt_id],
    queryFn: () => projekteApi.spalten(panel!.projekt_id!),
    enabled: !!panel?.projekt_id,
  });

  const umschalten = useMutation({
    mutationFn: (a: ProjektAufgabe) => projektAufgabenApi.update(a.id, { erledigt: !a.erledigt_am }),
    onSuccess: (_, a) => {
      toast.erfolg(a.erledigt_am ? "Aufgabe wieder offen" : "Aufgabe erledigt");
      void queryClient.invalidateQueries({ queryKey: ["projekt-aufgaben"] });
    },
  });

  const heute = heuteIso();
  const oeffnen = (a: ProjektAufgabe) => (istOfficeHost() ? navigate(`/meine-aufgaben/${a.id}`) : setPanel(a));
  const neu = (
    <button type="button" onClick={() => setPanel(null)} className={ABSCHNITT_AKTION}>
      + Aufgabe
    </button>
  );

  return (
    <>
      {aufgaben.length === 0 ? (
        <div className="flex justify-end">{neu}</div>
      ) : (
        <Abschnitt titel="Aufgaben" aktion={neu}>
          <ul className="divide-y-[0.5px] divide-sep">
            {aufgaben.map((a) => {
              const f = a.erledigt_am ? null : faelligText(a.faelligkeit_am, heute);
              return (
                <li key={a.id} className="flex items-center gap-3 py-2">
                  <AbhakKreis
                    checked={!!a.erledigt_am}
                    onChange={() => umschalten.mutate(a)}
                    ariaLabel={a.erledigt_am ? `„${a.titel}“ wieder öffnen` : `„${a.titel}“ als erledigt markieren`}
                  />
                  <button
                    type="button"
                    onClick={() => oeffnen(a)}
                    className={`min-w-0 flex-1 truncate text-left text-fliess ${a.erledigt_am ? "text-label2 line-through" : "text-label"}`}
                  >
                    {a.titel}
                  </button>
                  {f && <span className={`shrink-0 text-sekundaer ${f.ueberfaellig ? "font-semibold text-st-fehlt" : "text-label2"}`}>{f.text}</span>}
                </li>
              );
            })}
          </ul>
        </Abschnitt>
      )}
      {panel !== undefined && (
        <ProjektAufgabeDetailPanel
          projektId={panel?.projekt_id ?? undefined}
          spalten={spalten ?? []}
          aufgabe={panel}
          vorbelegterVorgangId={panel === null ? vorgangId : undefined}
          vorbelegterAuftragId={panel === null ? auftragId : undefined}
          onClose={() => setPanel(undefined)}
        />
      )}
    </>
  );
}
