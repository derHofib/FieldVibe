import { useMutation, useQuery } from "@tanstack/react-query";

import { kundenportalApi } from "../../api/endpoints";
import { openPdfBlob } from "../../utils/pdf";
import type { Rechnung, RechnungStatus } from "../../types";

const STATUS_LABEL: Record<RechnungStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  bezahlt: "Bezahlt",
  storniert: "Storniert",
};

function RechnungZeile({ rechnung }: { rechnung: Rechnung }) {
  const pdfMutation = useMutation({
    mutationFn: () => kundenportalApi.rechnungPdf(rechnung.id),
    onSuccess: openPdfBlob,
  });

  return (
    <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs text-slate-400 dark:text-slate-500">{rechnung.rechnungsnummer}</div>
          <div className="font-medium text-slate-800 dark:text-slate-100">{rechnung.betrag_brutto} EUR</div>
          {rechnung.faellig_am && (
            <div className="text-xs text-slate-500 dark:text-slate-400">
              Fällig am {new Date(rechnung.faellig_am).toLocaleDateString("de-DE")}
            </div>
          )}
        </div>
        <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {STATUS_LABEL[rechnung.status]}
        </span>
      </div>
      <button
        onClick={() => pdfMutation.mutate()}
        disabled={pdfMutation.isPending}
        className="btn-touch mt-3 rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-slate-800 dark:text-slate-300"
      >
        📄 PDF anzeigen
      </button>
    </div>
  );
}

export function PortalRechnungenPage() {
  const { data: rechnungen, isLoading } = useQuery({
    queryKey: ["portal-rechnungen"],
    queryFn: kundenportalApi.rechnungen,
  });

  if (isLoading) return <p className="text-center text-slate-500 dark:text-slate-400">Lädt…</p>;

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold text-slate-800 dark:text-slate-100">Ihre Rechnungen</h1>
      {!rechnungen || rechnungen.length === 0 ? (
        <p className="text-sm text-slate-400 dark:text-slate-500">Keine Rechnungen vorhanden.</p>
      ) : (
        <div className="space-y-2">
          {rechnungen.map((r) => (
            <RechnungZeile key={r.id} rechnung={r} />
          ))}
        </div>
      )}
    </div>
  );
}
