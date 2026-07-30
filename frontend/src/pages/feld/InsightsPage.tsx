import { useMutation, useQuery } from "@tanstack/react-query";
import { Navigate, useNavigate } from "react-router-dom";

import { exportApi, insightsApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import { downloadBlob } from "../../utils/download";
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

function Kachel({ label, wert }: { label: string; wert: string }) {
  return (
    <div className="rounded-lg bg-white p-4 shadow-sm">
      <div className="text-xs font-medium text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-bold text-slate-800">{wert}</div>
    </div>
  );
}

export function InsightsPage() {
  const { currentUser } = useAuth();
  const navigate = useNavigate();

  const { data: insights, isLoading } = useQuery({
    queryKey: ["insights"],
    queryFn: insightsApi.get,
  });

  const vorgaengeExportMutation = useMutation({
    mutationFn: exportApi.vorgaengeCsv,
    onSuccess: (blob) => downloadBlob(blob, "Vorgaenge.csv"),
  });
  const zeiterfassungExportMutation = useMutation({
    mutationFn: exportApi.zeiterfassungCsv,
    onSuccess: (blob) => downloadBlob(blob, "Zeiterfassung.csv"),
  });
  const materialExportMutation = useMutation({
    mutationFn: exportApi.materialCsv,
    onSuccess: (blob) => downloadBlob(blob, "Material-Bestand.csv"),
  });

  if (currentUser && currentUser.role !== "mandant_admin") return <Navigate to="/feed" replace />;
  if (isLoading || !insights) return <p className="text-center text-slate-500">Lädt…</p>;

  const gesamtVorgaenge = Object.values(insights.vorgaenge_nach_status).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-slate-500">
        ← Zurück
      </button>
      <h1 className="text-lg font-bold text-slate-800">📊 Insights</h1>

      <div className="grid grid-cols-2 gap-3">
        <Kachel label="Offene Rechnungssumme" wert={`${insights.offene_rechnungssumme} EUR`} />
        <Kachel
          label="Angebots-Annahmequote"
          wert={
            insights.angebote_annahmequote !== null
              ? `${(insights.angebote_annahmequote * 100).toFixed(0)} %`
              : "—"
          }
        />
        <Kachel label="Angebote versendet" wert={String(insights.angebote_versendet)} />
        <Kachel label="Angebote angenommen" wert={String(insights.angebote_angenommen)} />
      </div>

      <div className="rounded-lg bg-white p-4 shadow-sm">
        <h2 className="mb-2 text-sm font-semibold text-slate-500">Vorgänge nach Status</h2>
        <div className="space-y-1.5">
          {Object.entries(insights.vorgaenge_nach_status).map(([status, count]) => (
            <div key={status} className="flex items-center gap-2">
              <span className="w-32 shrink-0 text-sm text-slate-600">
                {STATUS_LABEL[status as VorgangStatus] ?? status}
              </span>
              <div className="h-4 flex-1 overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-slate-700"
                  style={{ width: `${gesamtVorgaenge > 0 ? (count / gesamtVorgaenge) * 100 : 0}%` }}
                />
              </div>
              <span className="w-8 shrink-0 text-right text-sm font-medium text-slate-700">{count}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-lg bg-white p-4 shadow-sm">
        <h2 className="mb-2 text-sm font-semibold text-slate-500">Techniker-Auslastung (diese Woche)</h2>
        {insights.techniker_auslastung.length === 0 ? (
          <p className="text-sm text-slate-400">Keine Techniker erfasst.</p>
        ) : (
          <div className="space-y-1.5">
            {insights.techniker_auslastung.map((t) => (
              <div key={t.techniker_id} className="flex items-center justify-between text-sm">
                <span className="text-slate-700">{t.name}</span>
                <span className="font-medium text-slate-800">{t.stunden_diese_woche} Std.</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-lg bg-white p-4 shadow-sm">
        <h2 className="mb-2 text-sm font-semibold text-slate-500">Export</h2>
        <div className="space-y-2">
          <button
            onClick={() => vorgaengeExportMutation.mutate()}
            disabled={vorgaengeExportMutation.isPending}
            className="btn-touch w-full rounded-md bg-slate-100 px-3 py-2 text-sm font-medium text-slate-700 disabled:opacity-50"
          >
            ⬇️ Vorgänge (CSV)
          </button>
          <button
            onClick={() => zeiterfassungExportMutation.mutate()}
            disabled={zeiterfassungExportMutation.isPending}
            className="btn-touch w-full rounded-md bg-slate-100 px-3 py-2 text-sm font-medium text-slate-700 disabled:opacity-50"
          >
            ⬇️ Zeiterfassung (CSV)
          </button>
          <button
            onClick={() => materialExportMutation.mutate()}
            disabled={materialExportMutation.isPending}
            className="btn-touch w-full rounded-md bg-slate-100 px-3 py-2 text-sm font-medium text-slate-700 disabled:opacity-50"
          >
            ⬇️ Material-Bestand (CSV)
          </button>
        </div>
      </div>
    </div>
  );
}
