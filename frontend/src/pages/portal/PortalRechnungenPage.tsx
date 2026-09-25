import { useMutation, useQuery } from "@tanstack/react-query";
import { FileText, Receipt } from "lucide-react";
import { useState } from "react";

import { ApiError } from "../../api/client";
import { kundenportalApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import { RECHNUNG_STATUS_LABEL, istRechnungUeberfaellig } from "../../utils/buchhaltung";
import { openPdfBlob } from "../../utils/pdf";
import type { Rechnung } from "../../types";

function RechnungZeile({ rechnung }: { rechnung: Rechnung }) {
  const [fehler, setFehler] = useState<string | null>(null);
  const ueberfaellig = istRechnungUeberfaellig(rechnung);
  const pdfMutation = useMutation({
    mutationFn: () => kundenportalApi.rechnungPdf(rechnung.id),
    onSuccess: openPdfBlob,
    onError: (err) =>
      setFehler(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen."),
  });

  return (
    <div className="border border-sep bg-card p-4">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs text-label2">Rechnung Nr. {rechnung.rechnungsnummer}</div>
          <div className="font-medium text-label">{rechnung.betrag_brutto} EUR</div>
          {rechnung.faellig_am && (
            <div className={`text-xs ${ueberfaellig ? "font-medium text-st-fehlt" : "text-label2"}`}>
              {ueberfaellig ? "Überfällig seit " : "Fällig am "}
              {new Date(rechnung.faellig_am).toLocaleDateString("de-DE")}
            </div>
          )}
        </div>
        <span
          className={
            ueberfaellig
              ? "border border-st-fehlt px-2 py-1 text-xs font-semibold text-st-fehlt"
              : "border border-sep px-2 py-1 text-xs font-semibold text-label"
          }
        >
          {ueberfaellig ? "Überfällig" : RECHNUNG_STATUS_LABEL[rechnung.status]}
        </span>
      </div>
      <button
        onClick={() => {
          setFehler(null);
          pdfMutation.mutate();
        }}
        disabled={pdfMutation.isPending}
        className="btn-touch mt-3 flex items-center justify-center gap-1 rounded-md bg-fill px-3 py-1.5 text-sm font-medium text-label disabled:opacity-50 "
      >
        <FileText size={14} strokeWidth={2} /> {pdfMutation.isPending ? "PDF wird geladen…" : "PDF anzeigen"}
      </button>
      {fehler && <p className="mt-1 text-xs text-st-fehlt ">{fehler}</p>}
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
      <h1 className="text-lg font-bold text-label">Ihre Rechnungen</h1>
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
