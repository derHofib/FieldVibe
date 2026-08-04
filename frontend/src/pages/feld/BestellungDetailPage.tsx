import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { bestellungenApi, lieferantenApi } from "../../api/endpoints";
import { downloadBlob } from "../../utils/download";
import { openPdfBlob } from "../../utils/pdf";
import type { BestellungStatus } from "../../types";

const STATUS_LABEL: Record<BestellungStatus, string> = {
  entwurf: "Entwurf",
  bestellt: "Bestellt",
  eingegangen: "Eingegangen",
};

export function BestellungDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: bestellung } = useQuery({
    queryKey: ["bestellung", id],
    queryFn: () => bestellungenApi.get(id!),
    enabled: !!id,
  });
  const { data: lieferanten } = useQuery({ queryKey: ["lieferanten"], queryFn: () => lieferantenApi.list() });

  const statusMutation = useMutation({
    mutationFn: (status: BestellungStatus) => bestellungenApi.update(id!, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bestellung", id] });
      queryClient.invalidateQueries({ queryKey: ["material"] });
      queryClient.invalidateQueries({ queryKey: ["material-bedarfe"] });
    },
  });

  const csvMutation = useMutation({
    mutationFn: () => bestellungenApi.csv(id!),
    onSuccess: (blob) => downloadBlob(blob, `${bestellung?.bestellnummer ?? "Bestellung"}.csv`),
  });

  const pdfMutation = useMutation({
    mutationFn: () => bestellungenApi.pdf(id!),
    onSuccess: openPdfBlob,
  });

  if (!bestellung) return <p className="text-center text-slate-500 dark:text-slate-400">Lädt…</p>;

  const lieferant = lieferanten?.find((l) => l.id === bestellung.lieferant_id);
  const gesamtRichtwert = bestellung.positionen.reduce(
    (sum, p) => sum + Number(p.menge) * Number(p.einzelpreis),
    0,
  );

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-slate-500 dark:text-slate-400">
        ← Zurück
      </button>

      <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs text-slate-400 dark:text-slate-500">{bestellung.bestellnummer}</div>
            <h1 className="text-lg font-bold text-slate-800 dark:text-slate-100">
              {lieferant?.name ?? "Kein Lieferant hinterlegt"}
            </h1>
          </div>
          <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            {STATUS_LABEL[bestellung.status]}
          </span>
        </div>
        {bestellung.notiz && (
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{bestellung.notiz}</p>
        )}
        <div className="mt-3 text-right text-sm text-slate-500 dark:text-slate-400">
          Richtwert gesamt: {gesamtRichtwert.toFixed(2)} EUR
        </div>

        <div className="mt-3 flex gap-2">
          <button
            onClick={() => csvMutation.mutate()}
            disabled={csvMutation.isPending}
            className="btn-touch flex-1 rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-slate-800 dark:text-slate-300"
          >
            ⬇️ CSV
          </button>
          <button
            onClick={() => pdfMutation.mutate()}
            disabled={pdfMutation.isPending}
            className="btn-touch flex-1 rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-slate-800 dark:text-slate-300"
          >
            📄 PDF
          </button>
        </div>
      </div>

      <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
        <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-slate-400">Positionen</h2>
        <div className="space-y-1.5">
          {bestellung.positionen.map((p) => (
            <div
              key={p.id}
              className="flex items-center justify-between rounded-md bg-slate-50 p-2 text-sm dark:bg-slate-800/60"
            >
              <div>
                <div className="text-slate-700 dark:text-slate-300">{p.beschreibung}</div>
                <div className="text-xs text-slate-400 dark:text-slate-500">
                  {p.menge} {p.einheit} × {p.einzelpreis} EUR (Richtwert)
                </div>
              </div>
              <div className="font-medium text-slate-700 dark:text-slate-300">
                {(Number(p.menge) * Number(p.einzelpreis)).toFixed(2)} EUR
              </div>
            </div>
          ))}
        </div>
      </div>

      {bestellung.status === "entwurf" && (
        <div className="flex gap-2">
          <button
            onClick={() => statusMutation.mutate("bestellt")}
            disabled={statusMutation.isPending}
            className="btn-touch flex-1 rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Als bestellt markieren
          </button>
          <button
            onClick={() => statusMutation.mutate("eingegangen")}
            disabled={statusMutation.isPending}
            className="btn-touch rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-slate-800 dark:text-slate-300"
          >
            Wareneingang buchen
          </button>
        </div>
      )}
      {bestellung.status === "bestellt" && (
        <button
          onClick={() => statusMutation.mutate("eingegangen")}
          disabled={statusMutation.isPending}
          className="btn-touch w-full rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Wareneingang buchen
        </button>
      )}
      {bestellung.status === "eingegangen" && (
        <p className="text-center text-sm text-slate-400 dark:text-slate-500">
          Wareneingang gebucht -- Bestand wurde entsprechend erhöht.
        </p>
      )}
    </div>
  );
}
