import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { vorgaengeApi } from "../../api/endpoints";
import { Monogramm } from "../../components/apple/Monogramm";
import {
  KANBAN_SPALTEN,
  STATUS_LABEL,
  istUeberfaellig,
  tageSeit,
} from "../../config/vorgangDarstellung";
import type { FeedCard, VorgangStatus } from "../../types";

/** Spalten nach Status, per Drag&Drop verschiebbar. Ein Statuswechsel kann im
 * Backend Folgelogik ausloesen (Pflichtformular-Pruefung bei "abgeschlossen",
 * Wiedervorlage bei "wartet_kunde") und dabei ablehnen (409) -- deshalb rein
 * optimistisch: die Karte springt sofort in die Zielspalte, bei einem Fehler
 * vom Server aber zurueck in die Ausgangsspalte samt Meldung, statt die Karte
 * einfach dort verschwinden zu lassen. */
export function VorgaengeKanban({ vorgaenge }: { vorgaenge: FeedCard[] }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [optimistisch, setOptimistisch] = useState<Record<string, VorgangStatus>>({});
  const [fehler, setFehler] = useState<string | null>(null);

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: VorgangStatus }) =>
      vorgaengeApi.update(id, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["feed"] });
    },
    onError: (err, { id }) => {
      setFehler(err instanceof ApiError ? err.message : "Status konnte nicht geändert werden.");
      setOptimistisch((bisher) => {
        const naechste = { ...bisher };
        delete naechste[id];
        return naechste;
      });
    },
    onSettled: (_data, error, { id }) => {
      if (!error) {
        setOptimistisch((bisher) => {
          const naechste = { ...bisher };
          delete naechste[id];
          return naechste;
        });
      }
    },
  });

  const effektiverStatus = (v: FeedCard): VorgangStatus => optimistisch[v.id] ?? v.status;
  const nachStatus = (status: VorgangStatus) => vorgaenge.filter((v) => effektiverStatus(v) === status);

  const handleDrop = (zielStatus: VorgangStatus, vorgangId: string) => {
    const vorgang = vorgaenge.find((v) => v.id === vorgangId);
    if (!vorgang || effektiverStatus(vorgang) === zielStatus) return;
    setOptimistisch((bisher) => ({ ...bisher, [vorgangId]: zielStatus }));
    statusMutation.mutate({ id: vorgangId, status: zielStatus });
  };

  return (
    <div>
      {fehler && (
        <div className="mb-3 flex items-center justify-between gap-2 rounded-lg bg-st-fehlt-bg px-3 py-2 text-sm text-st-fehlt">
          <span className="flex items-center gap-1.5">
            <AlertTriangle size={14} strokeWidth={2} aria-hidden="true" /> {fehler}
          </span>
          <button onClick={() => setFehler(null)} className="text-xs underline">
            Ausblenden
          </button>
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
        {KANBAN_SPALTEN.map((status) => {
          const spalte = nachStatus(status);
          return (
            <div
              key={status}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const vorgangId = e.dataTransfer.getData("text/plain");
                if (vorgangId) handleDrop(status, vorgangId);
              }}
              className="min-w-0 rounded-lg"
            >
              <div className="mb-2 flex items-center justify-between px-1">
                <span className="text-xs font-bold text-label2">
                  {STATUS_LABEL[status]}
                </span>
                <span className="rounded-full bg-fill px-1.5 text-[10px] font-bold text-label3">
                  {spalte.length}
                </span>
              </div>

              <div className="min-h-[64px] space-y-2">
                {spalte.map((v) => {
                  const ueberfaellig = istUeberfaellig(v.faelligkeit_am);
                  return (
                    <div
                      key={v.id}
                      draggable
                      onDragStart={(e) => {
                        e.dataTransfer.setData("text/plain", v.id);
                        e.dataTransfer.effectAllowed = "move";
                      }}
                      className="card-interactive card-ap w-full cursor-grab p-3"
                      // .card-ap setzt den Rahmen als CSS-Shorthand ausserhalb
                      // jedes @layer -- eine Tailwind-Randfarb-Utility (im
                      // "utilities"-Layer) koennte das nie ueberschreiben,
                      // deshalb hier per Inline-Style statt Klasse.
                      style={ueberfaellig ? { borderColor: "var(--st-fehlt-dot)" } : undefined}
                    >
                      <button
                        type="button"
                        onClick={() => navigate(`/vorgaenge/${v.id}`)}
                        className="block w-full text-left"
                      >
                        <p className="text-[10.5px] font-bold text-label2">
                          {v.vorgangsnummer}
                        </p>
                        <p className="mt-0.5 text-[13px] font-semibold text-label">
                          {v.titel}
                        </p>
                        <p className="mt-2 truncate text-[11.5px] text-label2">
                          {v.kunde_name}
                        </p>
                        <div className="mt-1.5 flex items-center justify-between gap-2">
                          {ueberfaellig ? (
                            <span className="rounded-full bg-st-fehlt-bg px-2 py-0.5 text-[10px] font-semibold text-st-fehlt">
                              {tageSeit(v.faelligkeit_am!)} Tage
                            </span>
                          ) : (
                            <span />
                          )}
                          {v.zugewiesener_name && (
                            <span title={v.zugewiesener_name}>
                              <Monogramm name={v.zugewiesener_name} groesse={20} />
                            </span>
                          )}
                        </div>
                      </button>
                      {/* Tastatur-/Screenreader-Alternative zum Drag&Drop-Statuswechsel
                          -- die Karte selbst ist nur per Maus zwischen Spalten
                          verschiebbar. */}
                      <label htmlFor={`kanban-status-${v.id}`} className="sr-only">
                        Status von „{v.titel}“ ändern
                      </label>
                      <select
                        id={`kanban-status-${v.id}`}
                        value={effektiverStatus(v)}
                        onChange={(e) => handleDrop(e.target.value as VorgangStatus, v.id)}
                        className="field-ap mt-1.5 h-auto px-1 py-0.5 text-[10px]"
                      >
                        {KANBAN_SPALTEN.map((s) => (
                          <option key={s} value={s}>
                            {STATUS_LABEL[s]}
                          </option>
                        ))}
                      </select>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
