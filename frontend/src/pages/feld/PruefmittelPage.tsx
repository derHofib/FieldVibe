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
  if (datum < heute) return "text-st-fehlt ";
  const in7Tagen = new Date();
  in7Tagen.setDate(in7Tagen.getDate() + 7);
  if (datum <= in7Tagen.toISOString().slice(0, 10)) return "text-st-arbeit ";
  return "text-label2";
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
  const { currentUser, hatRecht } = useAuth();
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

  const deleteMutation = useMutation({
    mutationFn: (id: string) => pruefmittelApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["pruefmittel"] }),
  });

  const kannLoeschen = currentUser?.role === "loesch_operativ";

  if (currentUser && !hatRecht("material", "sehen")) return <Navigate to="/feed" replace />;

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
        <button onClick={() => navigate(-1)} className="text-sm text-label2">
          ← Zurück
        </button>
        <h1 className="text-lg font-bold text-label">Prüfmittelverwaltung</h1>
        <span />
      </div>

      <button
        onClick={() => setShowForm((v) => !v)}
        className="btn-touch rounded-md btn-ap-primary px-4 py-2 text-sm font-medium"
      >
        {showForm ? "Abbrechen" : "+ Neues Prüfmittel"}
      </button>

      {showForm && (
        <div className="space-y-3 card-ap p-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-label2">
              Bezeichnung
            </label>
            <input
              value={form.bezeichnung}
              onChange={(e) => setForm({ ...form, bezeichnung: e.target.value })}
              className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              placeholder="z.B. Installationstester Gossen Metrahit"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-label2">
              Seriennummer
            </label>
            <input
              value={form.seriennummer}
              onChange={(e) => setForm({ ...form, seriennummer: e.target.value })}
              className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-label2">
              Zugewiesen an
            </label>
            <select
              value={form.zugewiesenAn}
              onChange={(e) => setForm({ ...form, zugewiesenAn: e.target.value })}
              className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
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
            <label className="mb-1 block text-xs font-medium text-label2">
              Kalibrierintervall (Monate)
            </label>
            <input
              type="number"
              min={1}
              value={form.intervallMonate}
              onChange={(e) => setForm({ ...form, intervallMonate: e.target.value })}
              className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
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
            className="btn-touch w-full rounded-md btn-ap-primary px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
      )}

      <div className="space-y-2">
        {sortiert.length === 0 ? (
          <p className="text-center text-sm text-label2">Keine Prüfmittel erfasst.</p>
        ) : (
          sortiert.map((mittel) => (
            <div
              key={mittel.id}
              className="card-ap p-3"
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-sm font-medium text-label">
                    {mittel.bezeichnung}
                  </div>
                  {mittel.seriennummer && (
                    <div className="text-xs text-label2">SN {mittel.seriennummer}</div>
                  )}
                  <div className="text-xs text-label2">
                    Zugewiesen: {nameFuer(mittel.zugewiesen_an)}
                  </div>
                </div>
                <span className="border border-sep px-2 py-0.5 text-xs text-label">
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
                  className="btn-touch rounded-md bg-fill px-3 py-1 text-xs font-medium text-label disabled:opacity-50 "
                >
                  Kalibrierung erfolgt (heute)
                </button>
              </div>
              {kannLoeschen && (
                <button
                  onClick={() => {
                    if (window.confirm(`Prüfmittel "${mittel.bezeichnung}" wirklich löschen?`)) {
                      deleteMutation.mutate(mittel.id);
                    }
                  }}
                  disabled={deleteMutation.isPending}
                  className="btn-touch mt-2 w-full rounded-md border border-st-fehlt py-1 text-xs font-medium text-st-fehlt disabled:opacity-50 "
                >
                  Löschen
                </button>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
