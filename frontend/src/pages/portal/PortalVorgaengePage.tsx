import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { kundenportalApi } from "../../api/endpoints";
import type { VorgangStatus } from "../../types";

const STATUS_LABEL: Record<VorgangStatus, string> = {
  neu: "Neu",
  geplant: "Geplant",
  in_arbeit: "In Arbeit",
  wartet_kunde: "Wartet auf Kunde",
  abgeschlossen: "Abgeschlossen",
  abgerechnet: "Abgerechnet",
  storniert: "Storniert",
};

export function PortalVorgaengePage() {
  const navigate = useNavigate();
  const { data: vorgaenge, isLoading } = useQuery({
    queryKey: ["portal-vorgaenge"],
    queryFn: kundenportalApi.vorgaenge,
  });

  if (isLoading) return <p className="text-center text-slate-500 dark:text-slate-400">Lädt…</p>;

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold text-slate-800 dark:text-slate-100">Ihre Aufträge</h1>
      {!vorgaenge || vorgaenge.length === 0 ? (
        <p className="text-sm text-slate-400 dark:text-slate-500">Keine Aufträge vorhanden.</p>
      ) : (
        <div className="space-y-2">
          {vorgaenge.map((v) => (
            <button
              key={v.id}
              onClick={() => navigate(`/portal/vorgaenge/${v.id}`)}
              className="card-interactive btn-touch block w-full rounded-lg bg-white p-4 text-left shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800"
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-xs text-slate-400 dark:text-slate-500">{v.vorgangsnummer}</div>
                  <div className="font-medium text-slate-800 dark:text-slate-100">{v.titel}</div>
                </div>
                <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                  {STATUS_LABEL[v.status]}
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
