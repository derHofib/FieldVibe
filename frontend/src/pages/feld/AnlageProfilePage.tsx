import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { anlagenApi, pruefzyklenApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";

const STATUS_BADGE: Record<string, string> = {
  neu: "bg-blue-100 text-blue-800",
  geplant: "bg-purple-100 text-purple-800",
  in_arbeit: "bg-amber-100 text-amber-800",
  wartet_kunde: "bg-orange-100 text-orange-800",
  abgeschlossen: "bg-green-100 text-green-800",
  abgerechnet: "bg-slate-200 text-slate-700",
  storniert: "bg-red-100 text-red-800",
};

function faelligkeitsFarbe(datum: string): string {
  const heute = new Date().toISOString().slice(0, 10);
  if (datum < heute) return "text-red-600";
  const in7Tagen = new Date();
  in7Tagen.setDate(in7Tagen.getDate() + 7);
  if (datum <= in7Tagen.toISOString().slice(0, 10)) return "text-amber-600";
  return "text-slate-500";
}

export function AnlageProfilePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser } = useAuth();
  const kannVerwalten =
    currentUser?.role === "mandant_admin" || currentUser?.role === "disponent";

  const [showForm, setShowForm] = useState(false);
  const [bezeichnung, setBezeichnung] = useState("");
  const [intervall, setIntervall] = useState("12");

  const { data: profil, isLoading } = useQuery({
    queryKey: ["anlage-profil", id],
    queryFn: () => anlagenApi.profil(id!),
    enabled: !!id,
  });
  const { data: pruefzyklen } = useQuery({
    queryKey: ["pruefzyklen", id],
    queryFn: () => pruefzyklenApi.list(id!),
    enabled: !!id,
  });

  const createMutation = useMutation({
    mutationFn: pruefzyklenApi.create,
    onSuccess: () => {
      setShowForm(false);
      setBezeichnung("");
      setIntervall("12");
      queryClient.invalidateQueries({ queryKey: ["pruefzyklen", id] });
    },
  });

  const markiereGeprueftMutation = useMutation({
    mutationFn: (pruefzyklusId: string) =>
      pruefzyklenApi.update(pruefzyklusId, {
        letzte_pruefung_am: new Date().toISOString().slice(0, 10),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["pruefzyklen", id] }),
  });

  if (isLoading || !profil) return <p className="text-center text-slate-500">Lädt…</p>;

  const adresse = profil.adresse as { strasse?: string; ort?: string };

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-slate-500">
        ← Zurück
      </button>

      <div className="rounded-lg bg-white p-4 shadow-sm">
        <h1 className="text-lg font-bold text-slate-800">{profil.bezeichnung}</h1>
        <button
          onClick={() => navigate(`/kunden/${profil.kunde.id}`)}
          className="text-sm text-blue-700 underline-offset-2 hover:underline"
        >
          {profil.kunde.name}
        </button>
        {(adresse?.strasse || adresse?.ort) && (
          <p className="mt-1 text-sm text-slate-500">
            {[adresse.strasse, adresse.ort].filter(Boolean).join(", ")}
          </p>
        )}
        {profil.anlagentyp && <p className="text-xs text-slate-400">{profil.anlagentyp}</p>}
        {profil.qr_code && <p className="mt-2 text-xs text-slate-400">QR-Code: {profil.qr_code}</p>}
        {profil.tags.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {profil.tags.map((t) => (
              <span key={t.id} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                #{t.label}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-lg bg-white p-4 shadow-sm">
        <h2 className="mb-2 text-sm font-semibold text-slate-500">Auswertung</h2>
        <div className="flex flex-wrap gap-2">
          {Object.entries(profil.vorgaenge_nach_status).map(([status, anzahl]) => (
            <span
              key={status}
              className={`rounded-full px-2 py-1 text-xs font-semibold ${STATUS_BADGE[status] ?? "bg-slate-100 text-slate-600"}`}
            >
              {anzahl}× {status}
            </span>
          ))}
        </div>
        <p className="mt-2 text-sm text-slate-600">
          Erfasste Zeit gesamt: <span className="font-medium">{profil.zeiterfassung_stunden_gesamt} Std.</span>
        </p>
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold text-slate-500">Vorgänge</h2>
        {profil.vorgaenge.length === 0 ? (
          <p className="text-sm text-slate-400">Keine Vorgänge.</p>
        ) : (
          <div className="space-y-2">
            {profil.vorgaenge.map((v) => (
              <button
                key={v.id}
                onClick={() => navigate(`/vorgaenge/${v.id}`)}
                className="btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-sm"
              >
                <div>
                  <div className="text-xs text-slate-400">
                    {v.vorgangsnummer}
                    {v.dauerauftrag_id && " · 🔁"}
                  </div>
                  <div className="text-sm font-medium text-slate-800">{v.titel}</div>
                </div>
                <span className={`rounded-full px-2 py-1 text-xs font-semibold ${STATUS_BADGE[v.status]}`}>
                  {v.status}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-500">Prüfzyklen</h2>
          {kannVerwalten && (
            <button
              onClick={() => setShowForm((v) => !v)}
              className="btn-touch text-xs font-medium text-blue-700"
            >
              {showForm ? "Abbrechen" : "+ Neuer Zyklus"}
            </button>
          )}
        </div>

        {showForm && (
          <div className="mb-2 space-y-2 rounded-lg bg-white p-3 shadow-sm">
            <input
              value={bezeichnung}
              onChange={(e) => setBezeichnung(e.target.value)}
              placeholder="z.B. E-Check ortsveränderliche Geräte"
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            />
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-500">Intervall (Monate)</label>
              <input
                type="number"
                min={1}
                value={intervall}
                onChange={(e) => setIntervall(e.target.value)}
                className="w-20 rounded-md border border-slate-300 px-2 py-1 text-sm"
              />
              <button
                disabled={!bezeichnung || createMutation.isPending}
                onClick={() =>
                  createMutation.mutate({
                    anlage_id: id!,
                    bezeichnung,
                    intervall_monate: Number(intervall),
                  })
                }
                className="btn-touch ml-auto rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Anlegen
              </button>
            </div>
          </div>
        )}

        {(pruefzyklen ?? []).length === 0 ? (
          <p className="text-sm text-slate-400">Keine Prüfzyklen erfasst.</p>
        ) : (
          <div className="space-y-2">
            {pruefzyklen!.map((z) => (
              <div key={z.id} className="rounded-lg bg-white p-3 shadow-sm">
                <div className="text-sm font-medium text-slate-800">{z.bezeichnung}</div>
                <div className="mt-1 flex items-center justify-between">
                  <span className={`text-sm font-medium ${faelligkeitsFarbe(z.naechste_pruefung_am)}`}>
                    Fällig: {new Date(z.naechste_pruefung_am).toLocaleDateString("de-DE")}
                  </span>
                  {kannVerwalten && (
                    <button
                      onClick={() => markiereGeprueftMutation.mutate(z.id)}
                      disabled={markiereGeprueftMutation.isPending}
                      className="btn-touch rounded-md bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700 disabled:opacity-50"
                    >
                      Prüfung erfolgt (heute)
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
