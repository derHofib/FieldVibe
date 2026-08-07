import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";

import { kundenportalApi } from "../../api/endpoints";
import { openPdfBlob } from "../../utils/pdf";
import type { AngebotStatus } from "../../types";

const STATUS_LABEL: Record<AngebotStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  angenommen: "Angenommen",
  abgelehnt: "Abgelehnt",
};

export function PortalAngebotDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: angebot } = useQuery({
    queryKey: ["portal-angebot", id],
    queryFn: () => kundenportalApi.angebot(id!),
    enabled: !!id,
  });

  const antwortMutation = useMutation({
    mutationFn: (status: "angenommen" | "abgelehnt") => kundenportalApi.antwortAufAngebot(id!, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portal-angebot", id] });
      queryClient.invalidateQueries({ queryKey: ["portal-angebote"] });
    },
  });

  const pdfMutation = useMutation({
    mutationFn: () => kundenportalApi.angebotPdf(id!),
    onSuccess: openPdfBlob,
  });

  if (!angebot) return <p className="text-center text-slate-500 dark:text-stone-400">Lädt…</p>;

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-slate-500 dark:text-stone-400">
        ← Zurück
      </button>

      <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <div className="flex items-start justify-between">
          <div className="text-xs text-slate-400 dark:text-stone-500">{angebot.angebotsnummer}</div>
          <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-stone-800 dark:text-stone-300">
            {STATUS_LABEL[angebot.status]}
          </span>
        </div>
        {angebot.gueltig_bis && (
          <p className="mt-1 text-xs text-slate-500 dark:text-stone-400">
            Gültig bis {new Date(angebot.gueltig_bis).toLocaleDateString("de-DE")}
          </p>
        )}
        <button
          onClick={() => pdfMutation.mutate()}
          disabled={pdfMutation.isPending}
          className="btn-touch mt-3 flex items-center justify-center gap-1 rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300"
        >
          <FileText size={14} strokeWidth={2} /> PDF anzeigen
        </button>
      </div>

      <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-stone-400">Positionen</h2>
        {angebot.positionen.length === 0 ? (
          <p className="text-sm text-slate-400 dark:text-stone-500">Keine Positionen.</p>
        ) : (
          <div className="space-y-1.5">
            {angebot.positionen.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between rounded-md bg-slate-50 p-2 text-sm dark:bg-stone-800/60"
              >
                <div>
                  <div className="text-slate-700 dark:text-stone-300">{p.beschreibung}</div>
                  <div className="text-xs text-slate-400 dark:text-stone-500">
                    {p.menge} {p.einheit} × {p.einzelpreis} EUR
                  </div>
                </div>
                <div className="font-medium text-slate-700 dark:text-stone-300">{p.gesamt} EUR</div>
              </div>
            ))}
          </div>
        )}
        <div className="mt-3 border-t border-slate-100 pt-2 text-right text-sm dark:border-stone-800">
          <div className="text-slate-500 dark:text-stone-400">Netto: {angebot.gesamt_netto} EUR</div>
          <div className="font-semibold text-slate-800 dark:text-stone-100">
            Brutto: {angebot.gesamt_brutto} EUR
          </div>
        </div>
      </div>

      {angebot.status === "versendet" && (
        <div className="flex gap-2">
          <button
            onClick={() => antwortMutation.mutate("angenommen")}
            disabled={antwortMutation.isPending}
            className="btn-touch flex-1 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Annehmen
          </button>
          <button
            onClick={() => antwortMutation.mutate("abgelehnt")}
            disabled={antwortMutation.isPending}
            className="btn-touch flex-1 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Ablehnen
          </button>
        </div>
      )}
      {angebot.status === "angenommen" && (
        <p className="text-center text-sm text-green-700 dark:text-green-400">
          Sie haben dieses Angebot angenommen.
        </p>
      )}
      {angebot.status === "abgelehnt" && (
        <p className="text-center text-sm text-red-700 dark:text-red-400">
          Sie haben dieses Angebot abgelehnt.
        </p>
      )}
    </div>
  );
}
