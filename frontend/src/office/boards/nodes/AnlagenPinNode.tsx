import { useQuery } from "@tanstack/react-query";
import { type NodeProps, useReactFlow } from "@xyflow/react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { anlagenApi } from "../../../api/endpoints";
import { SearchableSelect } from "../../../components/SearchableSelect";
import type { AnlagenPinDaten, BoardNode } from "../types";

/** Nummerierter Pin fuer die Bauplanung -- optional mit einer echten Anlage
 * verknuepft. Ohne Verknuepfung ist es ein reiner Positions-Marker (z.B.
 * "hier fehlt noch was zu klaeren"). */
export function AnlagenPinNode({ id, data, selected }: NodeProps<BoardNode>) {
  const navigate = useNavigate();
  const { updateNodeData } = useReactFlow();
  const { nummer, anlage_id } = data as AnlagenPinDaten;
  const [zeigePopover, setZeigePopover] = useState(false);

  const { data: anlage } = useQuery({
    queryKey: ["anlage", anlage_id],
    queryFn: () => anlagenApi.get(anlage_id!),
    enabled: !!anlage_id,
  });
  const { data: alleAnlagen } = useQuery({
    queryKey: ["anlagen"],
    queryFn: () => anlagenApi.list(),
    enabled: zeigePopover && !anlage_id,
  });

  return (
    <div className="relative">
      <button
        onClick={() => setZeigePopover((v) => !v)}
        className={`flex h-7 w-7 items-center justify-center rounded-full border-2 border-white bg-linear-to-r from-cyan-500 to-blue-600 text-xs font-extrabold text-white shadow-lg dark:border-stone-900 ${
          selected ? "ring-2 ring-blue-500 ring-offset-2" : ""
        }`}
      >
        {nummer}
      </button>
      {zeigePopover && (
        <div className="nodrag absolute top-9 left-1/2 z-10 w-60 -translate-x-1/2 rounded-xl border border-slate-100 bg-white p-3 shadow-xl dark:border-stone-800 dark:bg-stone-900">
          {anlage ? (
            <>
              <p className="text-[10px] font-bold tracking-wide text-slate-400 uppercase">Anlage</p>
              <p className="mt-0.5 text-sm font-bold text-ind-ink">{anlage.bezeichnung}</p>
              <div className="mt-2 flex items-center gap-3">
                <button
                  onClick={() => navigate(`/anlagen/${anlage.id}`)}
                  className="text-xs font-semibold text-blue-700 dark:text-blue-400"
                >
                  Anlage öffnen →
                </button>
                <button
                  onClick={() => updateNodeData(id, { anlage_id: null })}
                  className="text-xs font-medium text-ind-ink-3"
                >
                  Entfernen
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="mb-2 text-xs text-ind-ink-3">Noch keine Anlage verknüpft.</p>
              <SearchableSelect
                value=""
                onChange={(v) => {
                  updateNodeData(id, { anlage_id: v });
                  setZeigePopover(false);
                }}
                placeholder="Anlage suchen…"
                options={(alleAnlagen ?? []).map((a) => ({ value: a.id, label: a.bezeichnung }))}
              />
            </>
          )}
        </div>
      )}
    </div>
  );
}
