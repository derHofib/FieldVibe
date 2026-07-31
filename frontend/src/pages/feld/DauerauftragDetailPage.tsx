import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { anlagenApi, dauerauftraegeApi, kundenApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";

const STATUS_BADGE: Record<string, string> = {
  neu: "bg-blue-100 text-blue-800",
  geplant: "bg-purple-100 text-purple-800",
  in_arbeit: "bg-amber-100 text-amber-800",
  wartet_kunde: "bg-orange-100 text-orange-800",
  abgeschlossen: "bg-green-100 text-green-800",
  abgerechnet: "bg-slate-200 text-slate-700",
  storniert: "bg-slate-100 text-slate-400",
};

export function DauerauftragDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser } = useAuth();
  const kannVerwalten =
    currentUser?.role === "mandant_admin" || currentUser?.role === "disponent";

  const [editIntervall, setEditIntervall] = useState<string | null>(null);
  const [anlagenBearbeiten, setAnlagenBearbeiten] = useState(false);
  const [ausgewaehlteAnlageIds, setAusgewaehlteAnlageIds] = useState<string[]>([]);
  const [neueFaelligkeit, setNeueFaelligkeit] = useState(new Date().toISOString().slice(0, 10));

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
  const { data: anlagenListe } = useQuery({
    queryKey: ["anlagen", dauerauftrag?.kunde_id],
    queryFn: () => anlagenApi.list(dauerauftrag!.kunde_id),
    enabled: !!dauerauftrag,
  });
  const anlageNameById = new Map((anlagenListe ?? []).map((a) => [a.id, a.bezeichnung]));

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

  const deleteMutation = useMutation({
    mutationFn: () => dauerauftraegeApi.delete(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dauerauftraege"] });
      navigate("/dauerauftraege");
    },
  });

  const setAnlagenMutation = useMutation({
    mutationFn: () =>
      dauerauftraegeApi.setAnlagen(id!, {
        anlage_ids: ausgewaehlteAnlageIds,
        naechste_faelligkeit_am: neueFaelligkeit,
      }),
    onSuccess: () => {
      setAnlagenBearbeiten(false);
      queryClient.invalidateQueries({ queryKey: ["dauerauftrag", id] });
    },
  });

  function anlagenBearbeitenStarten() {
    setAusgewaehlteAnlageIds(
      (dauerauftrag!.ziele.filter((z) => z.anlage_id !== null).map((z) => z.anlage_id) as string[])
    );
    setAnlagenBearbeiten(true);
  }

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
          {dauerauftrag.anzahl_ziele <= 1 && (
            <div className="flex justify-between">
              <dt className="text-slate-500">Nächste Fälligkeit</dt>
              <dd className="text-slate-800">{dauerauftrag.naechste_faelligkeit_am ?? "–"}</dd>
            </div>
          )}
          <div className="flex justify-between">
            <dt className="text-slate-500">Modus</dt>
            <dd className="text-slate-800">
              {dauerauftrag.modus === "rollierend"
                ? "Rollierend ab Abschluss"
                : "Fest ab geplantem Termin"}
            </dd>
          </div>
          {(dauerauftrag.toleranz_frueh_tage !== null || dauerauftrag.toleranz_spaet_tage !== null) && (
            <div className="flex justify-between">
              <dt className="text-slate-500">Toleranz</dt>
              <dd className="text-slate-800">
                {dauerauftrag.toleranz_frueh_tage !== null && `-${dauerauftrag.toleranz_frueh_tage} Tage`}
                {dauerauftrag.toleranz_frueh_tage !== null && dauerauftrag.toleranz_spaet_tage !== null && " / "}
                {dauerauftrag.toleranz_spaet_tage !== null && `+${dauerauftrag.toleranz_spaet_tage} Tage`}
              </dd>
            </div>
          )}
          <div className="flex justify-between">
            <dt className="text-slate-500">Leistungstyp</dt>
            <dd className="text-slate-800">{dauerauftrag.leistungstyp}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500">Abrechnungsart</dt>
            <dd className="text-slate-800">{dauerauftrag.abrechnungsart}</dd>
          </div>
        </dl>

        <div className="mt-4">
          <div className="mb-1 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-500">
              Anlagen im Buendel ({dauerauftrag.anzahl_ziele})
            </h2>
            {kannVerwalten && !anlagenBearbeiten && (
              <button
                onClick={anlagenBearbeitenStarten}
                className="btn-touch text-xs text-blue-700 underline"
              >
                Anlagen verwalten
              </button>
            )}
          </div>

          {!anlagenBearbeiten ? (
            <div className="space-y-1">
              {dauerauftrag.ziele.map((z) => (
                <div
                  key={z.id}
                  className="flex items-center justify-between rounded-md bg-slate-50 px-2 py-1.5 text-sm"
                >
                  <span className="text-slate-700">
                    {z.anlage_id ? anlageNameById.get(z.anlage_id) ?? "Anlage" : "Ohne Anlagenbezug"}
                  </span>
                  <span className="text-xs text-slate-500">
                    {z.offener_vorgang_id ? (
                      <button
                        onClick={() => navigate(`/vorgaenge/${z.offener_vorgang_id}`)}
                        className="text-blue-700 underline"
                      >
                        Vorgang offen
                      </button>
                    ) : (
                      `fällig ${z.naechste_faelligkeit_am}`
                    )}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-2 rounded-md border border-slate-200 p-2">
              {!anlagenListe || anlagenListe.length === 0 ? (
                <p className="text-sm text-slate-400">Keine Anlagen für diesen Kunden vorhanden.</p>
              ) : (
                <div className="max-h-48 space-y-1 overflow-y-auto">
                  {anlagenListe.map((a) => (
                    <label key={a.id} className="flex items-center gap-2 py-1 text-sm text-slate-700">
                      <input
                        type="checkbox"
                        checked={ausgewaehlteAnlageIds.includes(a.id)}
                        onChange={(e) =>
                          setAusgewaehlteAnlageIds((prev) =>
                            e.target.checked ? [...prev, a.id] : prev.filter((id) => id !== a.id)
                          )
                        }
                      />
                      {a.bezeichnung}
                    </label>
                  ))}
                </div>
              )}
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-700">
                  Fälligkeit für neu hinzugefügte Anlagen
                </label>
                <input
                  type="date"
                  value={neueFaelligkeit}
                  onChange={(e) => setNeueFaelligkeit(e.target.value)}
                  className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2"
                />
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setAnlagenMutation.mutate()}
                  disabled={setAnlagenMutation.isPending}
                  className="btn-touch flex-1 rounded-md bg-slate-900 py-2 text-sm font-medium text-white disabled:opacity-50"
                >
                  Speichern
                </button>
                <button
                  onClick={() => setAnlagenBearbeiten(false)}
                  className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm text-slate-600"
                >
                  Abbrechen
                </button>
              </div>
            </div>
          )}
        </div>

        {kannVerwalten && (
          <div className="mt-3 space-y-2">
            <button
              onClick={() => toggleAktivMutation.mutate()}
              disabled={toggleAktivMutation.isPending}
              className="btn-touch w-full rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 disabled:opacity-50"
            >
              {dauerauftrag.aktiv ? "Dauer-Auftrag pausieren" : "Dauer-Auftrag reaktivieren"}
            </button>
            <button
              onClick={() => {
                if (window.confirm("Dauer-Auftrag wirklich löschen? Bereits erzeugte Vorgänge bleiben erhalten.")) {
                  deleteMutation.mutate();
                }
              }}
              disabled={deleteMutation.isPending}
              className="btn-touch w-full rounded-md border border-red-300 py-2 text-sm font-medium text-red-700 disabled:opacity-50"
            >
              Dauer-Auftrag löschen
            </button>
          </div>
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
                className={`btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-sm ${
                  v.status === "storniert" ? "opacity-60 grayscale" : ""
                }`}
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
