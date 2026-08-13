import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardList, FileText } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { vorgangFormulareApi } from "../api/endpoints";
import { openPdfBlob } from "../utils/pdf";

const VORGANG_STATUS_GESCHLOSSEN = new Set(["abgeschlossen", "abgerechnet", "storniert"]);

export function FormularAbschnitt({ vorgangId, vorgangStatus }: { vorgangId: string; vorgangStatus: string }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: verfuegbar } = useQuery({
    queryKey: ["vorgang-formulare-verfuegbar", vorgangId],
    queryFn: () => vorgangFormulareApi.verfuegbar(vorgangId),
  });
  const { data: ausfuellungen } = useQuery({
    queryKey: ["vorgang-formulare", vorgangId],
    queryFn: () => vorgangFormulareApi.list(vorgangId),
  });

  const startMutation = useMutation({
    mutationFn: (formularId: string) => vorgangFormulareApi.start(vorgangId, formularId),
    onSuccess: (vf) => {
      queryClient.invalidateQueries({ queryKey: ["vorgang-formulare", vorgangId] });
      navigate(`/vorgang-formulare/${vf.id}`);
    },
  });

  const pdfMutation = useMutation({
    mutationFn: (id: string) => vorgangFormulareApi.pdf(id),
    onSuccess: openPdfBlob,
  });

  const geschlossen = VORGANG_STATUS_GESCHLOSSEN.has(vorgangStatus);

  if ((verfuegbar ?? []).length === 0 && (ausfuellungen ?? []).length === 0) {
    return null;
  }

  return (
    <div className="rounded-lg bg-white p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
      <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-stone-400">Formulare</h2>

      {(ausfuellungen ?? []).length > 0 && (
        <div className="mb-2 space-y-1.5">
          {ausfuellungen!.map((vf) => (
            <div
              key={vf.id}
              className="flex items-center justify-between gap-2 rounded-md bg-slate-50 p-2 dark:bg-stone-800/60"
            >
              <button
                onClick={() => navigate(`/vorgang-formulare/${vf.id}`)}
                className="btn-touch flex min-w-0 flex-1 items-center gap-2 text-left"
              >
                <ClipboardList size={16} className="shrink-0 text-slate-400 dark:text-stone-500" />
                <span className="truncate text-sm text-slate-700 dark:text-stone-200">
                  {vf.formular_snapshot.name}
                </span>
              </button>
              <span
                className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
                  vf.status === "abgeschlossen"
                    ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300"
                    : "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300"
                }`}
              >
                {vf.status === "abgeschlossen" ? "Abgeschlossen" : "Offen"}
              </span>
              {vf.status === "abgeschlossen" && (
                <button
                  onClick={() => pdfMutation.mutate(vf.id)}
                  className="btn-touch shrink-0 p-1 text-slate-400 hover:text-slate-600 dark:text-stone-500 dark:hover:text-stone-300"
                  aria-label="Als PDF öffnen"
                >
                  <FileText size={16} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {!geschlossen && (verfuegbar ?? []).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {verfuegbar!.map((f) => (
            <button
              key={f.id}
              onClick={() => startMutation.mutate(f.id)}
              disabled={startMutation.isPending}
              className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-600 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300"
            >
              + {f.name} ausfüllen
              {f.pflicht_vor_abschluss && <span className="ml-1 text-rose-500">*</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
