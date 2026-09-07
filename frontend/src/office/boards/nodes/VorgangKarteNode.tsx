import { Handle, Position, useReactFlow, type NodeProps } from "@xyflow/react";
import { useQuery } from "@tanstack/react-query";
import { Link2 } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { kundenApi, vorgaengeApi } from "../../../api/endpoints";
import { SearchableSelect } from "../../../components/SearchableSelect";
import { STATUS_BADGE, STATUS_LABEL } from "../../../config/vorgangDarstellung";
import type { BoardNode, VorgangKarteDaten } from "../types";

/** Alleinstellungsmerkmal gegenueber Miro/generischen Whiteboards: dieses
 * Board-Element ist keine Notiz, sondern ein echter, live verlinkter
 * Vorgang -- Status/Titel kommen direkt aus der API statt im Board
 * einzufrieren, ein Klick fuehrt zur echten Detailseite. Frisch aus der
 * Werkzeugleiste erzeugt hat der Node noch keinen vorgang_id -- dann zeigt
 * er stattdessen eine Auswahl. */
export function VorgangKarteNode({ id, data, selected }: NodeProps<BoardNode>) {
  const navigate = useNavigate();
  const { updateNodeData } = useReactFlow();
  const { vorgang_id } = data as VorgangKarteDaten;

  const { data: vorgang } = useQuery({
    queryKey: ["vorgang", vorgang_id],
    queryFn: () => vorgaengeApi.get(vorgang_id),
    enabled: !!vorgang_id,
  });
  const { data: kunde } = useQuery({
    queryKey: ["kunde", vorgang?.kunde_id],
    queryFn: () => kundenApi.get(vorgang!.kunde_id),
    enabled: !!vorgang?.kunde_id,
  });
  const { data: alleVorgaenge } = useQuery({
    queryKey: ["vorgaenge-alle"],
    queryFn: () => vorgaengeApi.list(),
    enabled: !vorgang_id,
  });

  if (!vorgang_id) {
    return (
      <div
        className={`w-[210px] rounded-xl border-2 border-dashed border-indigo-300 bg-indigo-50/60 p-3 dark:border-indigo-500/40 dark:bg-indigo-500/10 ${
          selected ? "ring-2 ring-blue-500" : ""
        }`}
      >
        <p className="mb-2 flex items-center gap-1.5 text-[11px] font-bold text-indigo-600 dark:text-indigo-300">
          <Link2 size={12} strokeWidth={2.5} /> Vorgang verknüpfen
        </p>
        <SearchableSelect
          value=""
          onChange={(v) => updateNodeData(id, { vorgang_id: v })}
          placeholder="Vorgang suchen…"
          options={(alleVorgaenge ?? []).map((v) => ({ value: v.id, label: `${v.vorgangsnummer} · ${v.titel}` }))}
        />
      </div>
    );
  }

  return (
    <div
      onClick={() => navigate(`/vorgaenge/${vorgang_id}`)}
      className={`relative w-[210px] cursor-pointer overflow-hidden rounded-xl bg-white shadow-lg dark:bg-stone-900 ${
        selected ? "ring-2 ring-blue-500" : ""
      }`}
    >
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !border-none !bg-slate-300 dark:!bg-stone-600" />
      <span className="absolute -top-2 -right-2 flex h-5 w-5 items-center justify-center rounded-full border-2 border-white bg-indigo-100 text-indigo-600 dark:border-stone-900 dark:bg-indigo-500/20 dark:text-indigo-300">
        <Link2 size={11} strokeWidth={2.5} />
      </span>
      <div className="h-1 bg-linear-to-r from-cyan-500 to-blue-600" />
      <div className="p-3">
        {vorgang ? (
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-[10px] font-bold text-ind-ink-3">{vorgang.vorgangsnummer}</p>
              <p className="mt-0.5 truncate text-[13px] font-bold text-ind-ink">
                {vorgang.titel}
              </p>
              {kunde && (
                <p className="mt-0.5 truncate text-[11.5px] text-ind-ink-3">{kunde.name}</p>
              )}
            </div>
            <span
              className={`shrink-0 px-2 py-0.5 text-[10px] font-bold whitespace-nowrap ${STATUS_BADGE[vorgang.status]}`}
            >
              {STATUS_LABEL[vorgang.status]}
            </span>
          </div>
        ) : (
          <p className="text-xs text-ind-ink-3">Lädt…</p>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !border-none !bg-slate-300 dark:!bg-stone-600" />
    </div>
  );
}
