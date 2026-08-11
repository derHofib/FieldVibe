import { useMutation, useQuery } from "@tanstack/react-query";
import { FileText, Receipt } from "lucide-react";

import { kundenportalApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import { RECHNUNG_STATUS_LABEL } from "../../utils/buchhaltung";
import { openPdfBlob } from "../../utils/pdf";
import type { Rechnung } from "../../types";

function RechnungZeile({ rechnung }: { rechnung: Rechnung }) {
  const pdfMutation = useMutation({
    mutationFn: () => kundenportalApi.rechnungPdf(rechnung.id),
    onSuccess: openPdfBlob,
  });

  return (
    <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs text-slate-400 dark:text-stone-500">{rechnung.rechnungsnummer}</div>
          <div className="font-medium text-slate-800 dark:text-stone-100">{rechnung.betrag_brutto} EUR</div>
          {rechnung.faellig_am && (
            <div className="text-xs text-slate-500 dark:text-stone-400">
              Fällig am {new Date(rechnung.faellig_am).toLocaleDateString("de-DE")}
            </div>
          )}
        </div>
        <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-stone-800 dark:text-stone-300">
          {RECHNUNG_STATUS_LABEL[rechnung.status]}
        </span>
      </div>
      <button
        onClick={() => pdfMutation.mutate()}
        disabled={pdfMutation.isPending}
        className="btn-touch mt-3 flex items-center justify-center gap-1 rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300"
      >
        <FileText size={14} strokeWidth={2} /> PDF anzeigen
      </button>
    </div>
  );
}

export function PortalRechnungenPage() {
  const { data: rechnungen, isLoading } = useQuery({
    queryKey: ["portal-rechnungen"],
    queryFn: kundenportalApi.rechnungen,
  });

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold text-slate-800 dark:text-stone-100">Ihre Rechnungen</h1>
      {isLoading ? (
        <SkeletonList count={3} />
      ) : !rechnungen || rechnungen.length === 0 ? (
        <EmptyState icon={Receipt} text="Keine Rechnungen vorhanden." />
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
