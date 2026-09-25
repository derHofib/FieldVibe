import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KanbanSquare } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { auftraegeApi, projekteApi, vorgaengeApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { SeitenPanel } from "../../components/apple/SeitenPanel";
import { AUFTRAG_STATUS_LABEL } from "../auftraege/AuftraegeTabelle";
import { STATUS_BADGE, STATUS_LABEL } from "../../config/vorgangDarstellung";
import type { Projekt } from "../../types";

/** Detailinhalt fuer das rechte SeitenPanel -- Stammdaten editierbar,
 * darunter die verknuepften Auftraege (projekt_id-Filter) und die direkt
 * am Projekt haengenden Vorgaenge (projekt_id ohne Auftrag dazwischen,
 * siehe app/models/vorgang.py). "Kanban öffnen" wechselt in die
 * bestehende Aufgaben-Tafel (OfficeProjektePage.tsx), die fuer EIN
 * Projekt gebaut ist und hier bewusst nicht dupliziert wird. */
export function ProjektDetailPanel({
  projekt,
  onClose,
  onKanbanOeffnen,
}: {
  projekt: Projekt;
  onClose: () => void;
  onKanbanOeffnen: () => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState(projekt.name);

  const { data: aktuell } = useQuery({
    queryKey: ["projekte", projekt.id],
    queryFn: () => projekteApi.get(projekt.id),
    initialData: projekt,
  });

  const { data: auftraege } = useQuery({
    queryKey: ["auftraege", "projekt", projekt.id],
    queryFn: () => auftraegeApi.list({ projekt_id: projekt.id }),
  });

  const { data: vorgaenge } = useQuery({
    queryKey: ["vorgaenge", "projekt", projekt.id],
    queryFn: () => vorgaengeApi.list({ projekt_id: projekt.id }),
  });

  const aktualisieren = useMutation({
    mutationFn: (body: Parameters<typeof projekteApi.update>[1]) => projekteApi.update(projekt.id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projekte"] });
      queryClient.invalidateQueries({ queryKey: ["projekte", projekt.id] });
    },
  });

  return (
    <SeitenPanel
      offen
      titel={aktuell?.name ?? projekt.name}
      onClose={onClose}
      aktionen={
        <button onClick={onKanbanOeffnen} className="btn-ap flex items-center gap-1.5 text-xs">
          <KanbanSquare size={14} strokeWidth={2} aria-hidden="true" />
          Kanban öffnen
        </button>
      }
    >
      <div className="space-y-5 p-4">
        <div>
          <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-label3 uppercase">Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => name.trim() && name !== aktuell?.name && aktualisieren.mutate({ name: name.trim() })}
            className="field-ap"
          />
        </div>

        <label className="flex items-center gap-2 text-sm text-label">
          <input
            type="checkbox"
            checked={aktuell?.archiviert ?? projekt.archiviert}
            onChange={(e) => aktualisieren.mutate({ archiviert: e.target.checked })}
            className="h-4 w-4"
          />
          Archiviert
        </label>

        <div>
          <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-label3 uppercase">
            Aufträge ({auftraege?.length ?? 0})
          </label>
          {!auftraege || auftraege.length === 0 ? (
            <EmptyState icon={KanbanSquare} text="Noch kein Auftrag in diesem Projekt." />
          ) : (
            <div className="space-y-1.5">
              {auftraege.map((a) => (
                <div key={a.id} className="flex items-center justify-between gap-2 border border-sepstrong px-2.5 py-2 text-sm">
                  <span className="min-w-0 flex-1 truncate text-label">{a.titel}</span>
                  <span className="shrink-0 text-xs text-label2">{AUFTRAG_STATUS_LABEL[a.status]}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div>
          <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-label3 uppercase">
            Vorgänge direkt am Projekt ({vorgaenge?.length ?? 0})
          </label>
          {!vorgaenge || vorgaenge.length === 0 ? (
            <p className="text-sm text-label2">Keine Vorgänge direkt zugeordnet.</p>
          ) : (
            <div className="space-y-1.5">
              {vorgaenge.map((v) => (
                <button
                  key={v.id}
                  onClick={() => navigate(`/vorgaenge/${v.id}`)}
                  className="flex w-full items-center justify-between gap-2 border border-sepstrong px-2.5 py-2 text-left text-sm hover:bg-fill"
                >
                  <span className="min-w-0 flex-1 truncate text-label">
                    {v.vorgangsnummer} · {v.titel}
                  </span>
                  <span className={`shrink-0 rounded-[var(--radius-ap-pill)] px-2 py-0.5 text-[11px] font-semibold ${STATUS_BADGE[v.status]}`}>
                    {STATUS_LABEL[v.status]}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </SeitenPanel>
  );
}
