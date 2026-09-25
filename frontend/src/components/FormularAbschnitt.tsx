import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardList, FileText } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { formSubmissionsApi } from "../api/endpoints";
import { openPdfBlob } from "../utils/pdf";

const VORGANG_STATUS_GESCHLOSSEN = new Set(["abgeschlossen", "abgerechnet", "storniert"]);

export function FormularAbschnitt({ vorgangId, vorgangStatus }: { vorgangId: string; vorgangStatus: string }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: verfuegbar } = useQuery({
    queryKey: ["form-submissions-verfuegbar", vorgangId],
    queryFn: () => formSubmissionsApi.verfuegbar(vorgangId),
  });
  const { data: ausfuellungen } = useQuery({
    queryKey: ["form-submissions", vorgangId],
    queryFn: () => formSubmissionsApi.list(vorgangId),
  });

  const startMutation = useMutation({
    mutationFn: (schemaId: string) => formSubmissionsApi.start(vorgangId, schemaId),
    onSuccess: (submission) => {
      queryClient.invalidateQueries({ queryKey: ["form-submissions", vorgangId] });
      navigate(`/form-submissions/${submission.id}`);
    },
  });

  const pdfMutation = useMutation({
    mutationFn: (id: string) => formSubmissionsApi.pdf(id),
    onSuccess: openPdfBlob,
  });

  const geschlossen = VORGANG_STATUS_GESCHLOSSEN.has(vorgangStatus);

  if ((verfuegbar ?? []).length === 0 && (ausfuellungen ?? []).length === 0) {
    return null;
  }

  return (
    <div className="border border-sep bg-card p-3">
      <h2 className="mb-2 text-sm font-semibold text-label2">Formulare</h2>

      {(ausfuellungen ?? []).length > 0 && (
        <div className="mb-2 space-y-1.5">
          {ausfuellungen!.map((fs) => (
            <div
              key={fs.id}
              className="flex items-center justify-between gap-2 border border-sepstrong p-2"
            >
              <button
                onClick={() => navigate(`/form-submissions/${fs.id}`)}
                className="btn-touch flex min-w-0 flex-1 items-center gap-2 text-left"
              >
                <ClipboardList size={16} className="shrink-0 text-label2" />
                <span className="truncate text-sm text-label">{fs.schema_name}</span>
              </button>
              <span
                className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
                  fs.status === "abgeschlossen"
                    ? "bg-emerald-100 text-st-erledigt dark:bg-emerald-500/15 "
                    : "bg-amber-100 text-st-arbeit dark:bg-amber-500/15 "
                }`}
              >
                {fs.status === "abgeschlossen" ? "Abgeschlossen" : "Offen"}
              </span>
              {fs.status === "abgeschlossen" && (
                <button
                  onClick={() => pdfMutation.mutate(fs.id)}
                  className="btn-touch shrink-0 p-1 text-label2 hover:text-label 0 dark:hover:text-label3"
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
          {verfuegbar!.map((s) => (
            <button
              key={s.id}
              onClick={() => startMutation.mutate(s.id)}
              disabled={startMutation.isPending}
              className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-xs font-medium text-label disabled:opacity-50 dark:bg-stone-800 "
            >
              + {s.name} ausfüllen
              {s.pflicht_vor_abschluss && <span className="ml-1 text-st-fehlt">*</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
