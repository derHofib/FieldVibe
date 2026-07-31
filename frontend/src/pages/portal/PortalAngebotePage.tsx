import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { kundenportalApi } from "../../api/endpoints";
import type { AngebotStatus } from "../../types";

const STATUS_LABEL: Record<AngebotStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  angenommen: "Angenommen",
  abgelehnt: "Abgelehnt",
};

export function PortalAngebotePage() {
  const navigate = useNavigate();
  const { data: angebote, isLoading } = useQuery({
    queryKey: ["portal-angebote"],
    queryFn: kundenportalApi.angebote,
  });

  if (isLoading) return <p className="text-center text-slate-500 dark:text-slate-400">Lädt…</p>;

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold text-slate-800 dark:text-slate-100">Ihre Angebote</h1>
      {!angebote || angebote.length === 0 ? (
        <p className="text-sm text-slate-400 dark:text-slate-500">Keine Angebote vorhanden.</p>
      ) : (
        <div className="space-y-2">
          {angebote.map((a) => (
            <button
              key={a.id}
              onClick={() => navigate(`/portal/angebote/${a.id}`)}
              className="block w-full rounded-lg bg-white p-4 text-left shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800"
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-xs text-slate-400 dark:text-slate-500">{a.angebotsnummer}</div>
                  <div className="font-medium text-slate-800 dark:text-slate-100">{a.gesamt_brutto} EUR</div>
                </div>
                <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                  {STATUS_LABEL[a.status]}
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
