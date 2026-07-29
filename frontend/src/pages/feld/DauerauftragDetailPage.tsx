import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { dauerauftraegeApi, kundenApi } from "../../api/endpoints";
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

export function DauerauftragDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser } = useAuth();
  const kannVerwalten =
    currentUser?.role === "mandant_admin" || currentUser?.role === "disponent";

  const [editIntervall, setEditIntervall] = useState<string | null>(null);

  const { data: dauerauftrag, isLoading } = useQuery({
    queryKey: ["dauerauftrag", id],
    queryFn: () => dauerauftraegeApi.get(id!),
    enabled: !!id,
  });
  const { data: kunde } = useQuery({
    queryKey: ["kunde", dauerauftrag?.kunde_id],
    queryFn: () => kundenApi.get(dauerauftrag!.kunde_id),
    enabled: !!dauerauftrag,
  });

  const toggleAktivMutation = useMutation({
    mutationFn: () => dauerauftraegeApi.update(id!, { aktiv: !dauerauftrag!.aktiv }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["dauerauftrag", id] }),
  });

  const intervallMutation = useMutation({
    mutationFn: (intervall: number) => dauerauftraegeApi.update(id!, { intervall_tage: intervall }),
    onSuccess: () => {
      setEditIntervall(null);
      queryClient.invalidateQueries({ queryKey: ["dauerauftrag", id] });
    },
  });

  if (isLoading || !dauerauftrag) return <p className="text-center text-slate-500">Lädt…</p>;

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-slate-500">
        ← Zurück
      </button>

      <div className="rounded-lg bg-white p-4 shadow-sm">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-lg font-bold text-slate-800">{dauerauftrag.titel}</h1>
            {kunde && (
              <button
                onClick={() => navigate(`/kunden/${kunde.id}`)}
                className="text-sm text-blue-700 underline-offset-2 hover:underline"
              >
                {kunde.name}
              </button>
            )}
          </div>
          {!dauerauftrag.aktiv && (
            <span className="rounded-full bg-slate-200 px-2 py-1 text-xs text-slate-600">
              pausiert
            </span>
          )}
        </div>
        {dauerauftrag.beschreibung && (
          <p className="mt-2 text-sm text-slate-600">{dauerauftrag.beschreibung}</p>
        )}

        <dl className="mt-3 space-y-1 text-sm">
          <div className="flex justify-between">
            <dt className="text-slate-500">Intervall</dt>
            <dd className="text-slate-800">
              {editIntervall === null ? (
                <span className="flex items-center gap-2">
                  alle {dauerauftrag.intervall_tage} Tage
                  {kannVerwalten && (
                    <button
                      onClick={() => setEditIntervall(String(dauerauftrag.intervall_tage))}
                      className="btn-touch text-xs text-blue-700 underline"
                    >
                      ändern
                    </button>
                  )}
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <input
                    type="number"
                    min={1}
                    value={editIntervall}
                    onChange={(e) => setEditIntervall(e.target.value)}
                    className="w-16 rounded-md border border-slate-300 px-2 py-1"
                  />
                  Tage
                  <button
                    onClick={() => intervallMutation.mutate(Number(editIntervall))}
                    disabled={intervallMutation.isPending}
                    className="btn-touch rounded-md bg-slate-900 px-2 py-1 text-xs text-white disabled:opacity-50"
                  >
                    Speichern
                  </button>
                  <button
                    onClick={() => setEditIntervall(null)}
                    className="btn-touch text-xs text-slate-500 underline"
                  >
                    Abbrechen
                  </button>
                </span>
              )}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500">Nächste Fälligkeit</dt>
            <dd className="text-slate-800">{dauerauftrag.naechste_faelligkeit_am}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500">Leistungstyp</dt>
            <dd className="text-slate-800">{dauerauftrag.leistungstyp}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500">Abrechnungsart</dt>
            <dd className="text-slate-800">{dauerauftrag.abrechnungsart}</dd>
          </div>
        </dl>

        {kannVerwalten && (
          <button
            onClick={() => toggleAktivMutation.mutate()}
            disabled={toggleAktivMutation.isPending}
            className="btn-touch mt-3 w-full rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 disabled:opacity-50"
          >
            {dauerauftrag.aktiv ? "Dauer-Auftrag pausieren" : "Dauer-Auftrag reaktivieren"}
          </button>
        )}
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold text-slate-500">
          Verlauf ({dauerauftrag.vorgaenge.length} Vorgänge)
        </h2>
        {dauerauftrag.vorgaenge.length === 0 ? (
          <p className="text-sm text-slate-400">Noch kein Vorgang erzeugt.</p>
        ) : (
          <div className="space-y-2">
            {dauerauftrag.vorgaenge.map((v) => (
              <button
                key={v.id}
                onClick={() => navigate(`/vorgaenge/${v.id}`)}
                className="btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-sm"
              >
                <div>
                  <div className="text-xs text-slate-400">{v.vorgangsnummer}</div>
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
    </div>
  );
}
