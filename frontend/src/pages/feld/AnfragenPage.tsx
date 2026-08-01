import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate } from "react-router-dom";

import { anlagenApi, kundenApi, standorteApi, vorgangAnfragenApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { useAuth } from "../../context/AuthContext";
import type { Leistungstyp, VorgangAbrechnungsart, VorgangAnfrage } from "../../types";

const LEISTUNGSTYP_LABEL: Record<Leistungstyp, string> = {
  installation: "Installation",
  pruefung: "Prüfung",
  wartung: "Wartung",
  stoerung: "Störung",
  beratung: "Beratung",
  planung: "Planung",
};

const ABRECHNUNGSARTEN: { value: VorgangAbrechnungsart; label: string }[] = [
  { value: "aufwand", label: "Nach Aufwand" },
  { value: "pauschale", label: "Pauschale" },
  { value: "festpreis", label: "Festpreis" },
  { value: "wartungsvertrag", label: "Wartungsvertrag" },
  { value: "gewaehrleistung", label: "Gewährleistung" },
];

function AnfrageKarte({ anfrage }: { anfrage: VorgangAnfrage }) {
  const queryClient = useQueryClient();
  const [zeigeAnnehmen, setZeigeAnnehmen] = useState(false);
  const [zeigeAblehnen, setZeigeAblehnen] = useState(false);
  const [abrechnungsart, setAbrechnungsart] = useState<VorgangAbrechnungsart>("aufwand");
  const [ablehnungsgrund, setAblehnungsgrund] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: kunde } = useQuery({ queryKey: ["kunde", anfrage.kunde_id], queryFn: () => kundenApi.get(anfrage.kunde_id) });
  const { data: anlage } = useQuery({
    queryKey: ["anlage", anfrage.anlage_id],
    queryFn: () => anlagenApi.get(anfrage.anlage_id!),
    enabled: !!anfrage.anlage_id,
  });
  const { data: standort } = useQuery({
    queryKey: ["standort", anfrage.standort_id],
    queryFn: () => standorteApi.get(anfrage.standort_id!),
    enabled: !!anfrage.standort_id,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["vorgang-anfragen"] });

  const annehmenMutation = useMutation({
    mutationFn: () => vorgangAnfragenApi.annehmen(anfrage.id, { abrechnungsart }),
    onSuccess: invalidate,
    onError: (err) => setError(err instanceof ApiError ? err.message : "Fehler beim Annehmen"),
  });

  const ablehnenMutation = useMutation({
    mutationFn: () => vorgangAnfragenApi.ablehnen(anfrage.id, ablehnungsgrund || undefined),
    onSuccess: invalidate,
    onError: (err) => setError(err instanceof ApiError ? err.message : "Fehler beim Ablehnen"),
  });

  return (
    <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs text-slate-400 dark:text-slate-500">
            {kunde?.name ?? "…"}
            {standort && ` · ${standort.bezeichnung}`}
            {anlage && ` · ${anlage.bezeichnung}`}
          </div>
          <div className="text-sm font-medium text-slate-800 dark:text-slate-100">{anfrage.titel}</div>
          <span className="mt-1 inline-block rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            {LEISTUNGSTYP_LABEL[anfrage.leistungstyp]}
          </span>
        </div>
        {anfrage.status !== "offen" && (
          <span
            className={`rounded-full px-2 py-1 text-xs font-semibold ${
              anfrage.status === "angenommen"
                ? "bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300"
                : "bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300"
            }`}
          >
            {anfrage.status === "angenommen" ? "Angenommen" : "Abgelehnt"}
          </span>
        )}
      </div>
      {anfrage.beschreibung && (
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{anfrage.beschreibung}</p>
      )}
      {anfrage.ablehnungsgrund && (
        <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">Grund: {anfrage.ablehnungsgrund}</p>
      )}

      {anfrage.status === "offen" && (
        <div className="mt-3 space-y-2">
          {error && <p className="text-sm text-red-700 dark:text-red-400">{error}</p>}

          {!zeigeAnnehmen && !zeigeAblehnen && (
            <div className="flex gap-2">
              <button
                onClick={() => setZeigeAnnehmen(true)}
                className="btn-touch flex-1 rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 py-2 text-sm font-medium text-white"
              >
                Annehmen
              </button>
              <button
                onClick={() => setZeigeAblehnen(true)}
                className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 dark:border-slate-700 dark:text-slate-300"
              >
                Ablehnen
              </button>
            </div>
          )}

          {zeigeAnnehmen && (
            <div className="space-y-2 rounded-lg bg-slate-50 p-3 dark:bg-slate-800/60">
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400">Abrechnungsart</label>
              <select
                value={abrechnungsart}
                onChange={(e) => setAbrechnungsart(e.target.value as VorgangAbrechnungsart)}
                className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              >
                {ABRECHNUNGSARTEN.map((a) => (
                  <option key={a.value} value={a.value}>
                    {a.label}
                  </option>
                ))}
              </select>
              <div className="flex gap-2">
                <button
                  onClick={() => annehmenMutation.mutate()}
                  disabled={annehmenMutation.isPending}
                  className="btn-touch flex-1 rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 py-2 text-sm font-medium text-white disabled:opacity-50"
                >
                  Vorgang anlegen
                </button>
                <button
                  onClick={() => setZeigeAnnehmen(false)}
                  className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 dark:border-slate-700 dark:text-slate-300"
                >
                  Abbrechen
                </button>
              </div>
            </div>
          )}

          {zeigeAblehnen && (
            <div className="space-y-2 rounded-lg bg-slate-50 p-3 dark:bg-slate-800/60">
              <textarea
                value={ablehnungsgrund}
                onChange={(e) => setAblehnungsgrund(e.target.value)}
                placeholder="Grund (optional, für interne Notiz)"
                rows={2}
                className="w-full rounded-md border border-slate-300 p-2 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
              <div className="flex gap-2">
                <button
                  onClick={() => ablehnenMutation.mutate()}
                  disabled={ablehnenMutation.isPending}
                  className="btn-touch flex-1 rounded-md bg-red-600 py-2 text-sm font-medium text-white disabled:opacity-50"
                >
                  Ablehnen bestätigen
                </button>
                <button
                  onClick={() => setZeigeAblehnen(false)}
                  className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 dark:border-slate-700 dark:text-slate-300"
                >
                  Abbrechen
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function AnfragenPage() {
  const { currentUser } = useAuth();
  const [statusFilter, setStatusFilter] = useState<"offen" | "alle">("offen");

  const { data: anfragen, isLoading } = useQuery({
    queryKey: ["vorgang-anfragen", statusFilter],
    queryFn: () => vorgangAnfragenApi.list(statusFilter === "offen" ? "offen" : undefined),
  });

  if (currentUser && currentUser.role !== "mandant_admin" && currentUser.role !== "disponent") {
    return <Navigate to="/feed" replace />;
  }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-slate-800 dark:text-slate-100">Auftragsanfragen</h1>
      <div className="flex gap-2 rounded-lg bg-white p-1 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
        {(["offen", "alle"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setStatusFilter(f)}
            className={`btn-touch flex-1 rounded-md py-2 text-sm font-medium capitalize ${
              statusFilter === f
                ? "bg-gradient-to-r from-cyan-500 to-blue-600 text-white"
                : "text-slate-600 dark:text-slate-400"
            }`}
          >
            {f === "offen" ? "Offen" : "Alle"}
          </button>
        ))}
      </div>

      {isLoading ? (
        <p className="text-center text-slate-500 dark:text-slate-400">Lädt…</p>
      ) : !anfragen || anfragen.length === 0 ? (
        <p className="text-center text-sm text-slate-400 dark:text-slate-500">Keine Anfragen vorhanden.</p>
      ) : (
        <div className="space-y-2">
          {anfragen.map((a) => (
            <AnfrageKarte key={a.id} anfrage={a} />
          ))}
        </div>
      )}
    </div>
  );
}
