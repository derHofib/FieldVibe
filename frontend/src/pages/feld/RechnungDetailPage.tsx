import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { kundenApi, rechnungenApi } from "../../api/endpoints";
import { openPdfBlob } from "../../utils/pdf";
import type { RechnungStatus } from "../../types";

const STATUS_LABEL: Record<RechnungStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  bezahlt: "Bezahlt",
  storniert: "Storniert",
};

export function RechnungDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: rechnung } = useQuery({
    queryKey: ["rechnung", id],
    queryFn: () => rechnungenApi.get(id!),
    enabled: !!id,
  });
  const { data: kunde } = useQuery({
    queryKey: ["kunde", rechnung?.kunde_id],
    queryFn: () => kundenApi.get(rechnung!.kunde_id),
    enabled: !!rechnung,
  });

  const statusMutation = useMutation({
    mutationFn: (status: string) => rechnungenApi.updateStatus(id!, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["rechnung", id] }),
  });

  const pdfMutation = useMutation({
    mutationFn: () => rechnungenApi.pdf(id!),
    onSuccess: openPdfBlob,
  });

  if (!rechnung) return <p className="text-center text-slate-500">Lädt…</p>;

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-slate-500">
        ← Zurück
      </button>

      <div className="rounded-lg bg-white p-4 shadow-sm">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs text-slate-400">{rechnung.rechnungsnummer}</div>
            <h1 className="text-lg font-bold text-slate-800">{kunde?.name ?? "…"}</h1>
          </div>
          <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">
            {STATUS_LABEL[rechnung.status]}
          </span>
        </div>
        {rechnung.faellig_am && (
          <p className="mt-1 text-xs text-slate-500">
            Fällig am {new Date(rechnung.faellig_am).toLocaleDateString("de-DE")}
          </p>
        )}

        <div className="mt-3 text-right text-sm">
          <div className="text-slate-500">Netto: {rechnung.betrag_netto} EUR</div>
          <div className="font-semibold text-slate-800">Brutto: {rechnung.betrag_brutto} EUR</div>
        </div>

        <button
          onClick={() => pdfMutation.mutate()}
          disabled={pdfMutation.isPending}
          className="btn-touch mt-3 rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50"
        >
          📄 PDF anzeigen
        </button>
      </div>

      {rechnung.status === "entwurf" && (
        <div className="flex gap-2">
          <button
            onClick={() => statusMutation.mutate("versendet")}
            disabled={statusMutation.isPending}
            className="btn-touch flex-1 rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            An Kunden senden
          </button>
          <button
            onClick={() => statusMutation.mutate("storniert")}
            disabled={statusMutation.isPending}
            className="btn-touch rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-50"
          >
            Stornieren
          </button>
        </div>
      )}
      {rechnung.status === "versendet" && (
        <div className="flex gap-2">
          <button
            onClick={() => statusMutation.mutate("bezahlt")}
            disabled={statusMutation.isPending}
            className="btn-touch flex-1 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Als bezahlt markieren
          </button>
          <button
            onClick={() => statusMutation.mutate("storniert")}
            disabled={statusMutation.isPending}
            className="btn-touch rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-50"
          >
            Stornieren
          </button>
        </div>
      )}
    </div>
  );
}
