import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { pruefmittelApi, usersApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import type { Pruefmittel, PruefmittelStatus } from "../../types";

const STATUS_LABEL: Record<PruefmittelStatus, string> = {
  aktiv: "Aktiv",
  defekt: "Defekt",
  ausser_betrieb: "Außer Betrieb",
};

function faelligkeitsFarbe(datum: string): string {
  const heute = new Date().toISOString().slice(0, 10);
  if (datum < heute) return "text-red-600";
  const in7Tagen = new Date();
  in7Tagen.setDate(in7Tagen.getDate() + 7);
  if (datum <= in7Tagen.toISOString().slice(0, 10)) return "text-amber-600";
  return "text-slate-500";
}

function formatDatum(datum: string): string {
  return new Date(datum).toLocaleDateString("de-DE");
}

interface NeuesForm {
  bezeichnung: string;
  seriennummer: string;
  zugewiesenAn: string;
  intervallMonate: string;
}

export function PruefmittelPage() {
  const { currentUser } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<NeuesForm>({
    bezeichnung: "",
    seriennummer: "",
    zugewiesenAn: "",
    intervallMonate: "12",
  });

  const { data: pruefmittel } = useQuery({
    queryKey: ["pruefmittel"],
    queryFn: () => pruefmittelApi.list(),
  });
  const { data: users } = useQuery({ queryKey: ["users"], queryFn: usersApi.list });
  const zuweisbareNutzer = (users ?? []).filter((u) => u.aktiv);

  const createMutation = useMutation({
    mutationFn: pruefmittelApi.create,
    onSuccess: () => {
      setShowForm(false);
      setForm({ bezeichnung: "", seriennummer: "", zugewiesenAn: "", intervallMonate: "12" });
      queryClient.invalidateQueries({ queryKey: ["pruefmittel"] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof pruefmittelApi.update>[1] }) =>
      pruefmittelApi.update(id, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["pruefmittel"] }),
  });

  if (currentUser && currentUser.role === "techniker") return <Navigate to="/feed" replace />;

  const sortiert = [...(pruefmittel ?? [])].sort((a, b) =>
    a.naechste_kalibrierung_am.localeCompare(b.naechste_kalibrierung_am),
  );

  const nameFuer = (userId: string | null) => users?.find((u) => u.id === userId)?.name ?? "—";

  const markiereKalibriert = (mittel: Pruefmittel) => {
    updateMutation.mutate({
      id: mittel.id,
      body: { letzte_kalibrierung_am: new Date().toISOString().slice(0, 10) },
    });
  };

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sm text-slate-500">
          ← Zurück
        </button>
        <h1 className="text-lg font-bold text-slate-800">Prüfmittelverwaltung</h1>
        <span />
      </div>

      <button
        onClick={() => setShowForm((v) => !v)}
        className="btn-touch rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white"
      >
        {showForm ? "Abbrechen" : "+ Neues Prüfmittel"}
      </button>

      {showForm && (
        <div className="space-y-3 rounded-lg bg-white p-4 shadow-sm">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">Bezeichnung</label>
            <input
              value={form.bezeichnung}
              onChange={(e) => setForm({ ...form, bezeichnung: e.target.value })}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
              placeholder="z.B. Installationstester Gossen Metrahit"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">Seriennummer</label>
            <input
              value={form.seriennummer}
              onChange={(e) => setForm({ ...form, seriennummer: e.target.value })}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">Zugewiesen an</label>
            <select
              value={form.zugewiesenAn}
              onChange={(e) => setForm({ ...form, zugewiesenAn: e.target.value })}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            >
              <option value="">Niemand</option>
              {zuweisbareNutzer.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">
              Kalibrierintervall (Monate)
            </label>
            <input
              type="number"
              min={1}
              value={form.intervallMonate}
              onChange={(e) => setForm({ ...form, intervallMonate: e.target.value })}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            />
          </div>
          <button
            disabled={!form.bezeichnung || !form.intervallMonate || createMutation.isPending}
            onClick={() =>
              createMutation.mutate({
                bezeichnung: form.bezeichnung,
                seriennummer: form.seriennummer || undefined,
                zugewiesen_an: form.zugewiesenAn || undefined,
                kalibrierintervall_monate: Number(form.intervallMonate),
              })
            }
            className="btn-touch w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
      )}

      <div className="space-y-2">
        {sortiert.length === 0 ? (
          <p className="text-center text-sm text-slate-400">Keine Prüfmittel erfasst.</p>
        ) : (
          sortiert.map((mittel) => (
            <div key={mittel.id} className="rounded-lg bg-white p-3 shadow-sm">
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-sm font-medium text-slate-800">{mittel.bezeichnung}</div>
                  {mittel.seriennummer && (
                    <div className="text-xs text-slate-400">SN {mittel.seriennummer}</div>
                  )}
                  <div className="text-xs text-slate-500">Zugewiesen: {nameFuer(mittel.zugewiesen_an)}</div>
                </div>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                  {STATUS_LABEL[mittel.status]}
                </span>
              </div>
              <div className="mt-2 flex items-center justify-between">
                <span className={`text-sm font-medium ${faelligkeitsFarbe(mittel.naechste_kalibrierung_am)}`}>
                  Fällig: {formatDatum(mittel.naechste_kalibrierung_am)}
                </span>
                <button
                  onClick={() => markiereKalibriert(mittel)}
                  disabled={updateMutation.isPending}
                  className="btn-touch rounded-md bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700 disabled:opacity-50"
                >
                  Kalibrierung erfolgt (heute)
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
