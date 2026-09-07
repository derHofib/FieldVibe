import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { anlagenApi, dauerauftraegeApi, kundenApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";

const STATUS_BADGE: Record<string, string> = {
  neu: "border border-blue-400 text-blue-700 dark:border-blue-600 dark:text-blue-300",
  geplant: "border border-purple-400 text-purple-700 dark:border-purple-600 dark:text-purple-300",
  in_arbeit: "border border-amber-400 text-amber-700 dark:border-amber-600 dark:text-amber-300",
  wartet_kunde: "border border-orange-400 text-orange-700 dark:border-orange-600 dark:text-orange-300",
  abgeschlossen: "border border-green-400 text-green-700 dark:border-green-600 dark:text-green-300",
  abgerechnet: "border border-slate-400 text-slate-600 dark:border-stone-600 dark:text-stone-300",
  storniert: "border border-slate-300 text-slate-400 dark:border-stone-700 dark:text-stone-500",
};

export function DauerauftragDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { hatRecht } = useAuth();
  const kannVerwalten = hatRecht("dispo", "bearbeiten");

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

  if (isLoading || !dauerauftrag) return <p className="text-center text-ind-ink-3">Lädt…</p>;

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-ind-ink-3">
        ← Zurück
      </button>

      <div className="border border-ind-line bg-ind-bg p-4">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-lg font-bold text-ind-ink">{dauerauftrag.titel}</h1>
            {kunde && (
              <button
                onClick={() => navigate(`/kunden/${kunde.id}`)}
                className="text-sm text-blue-700 underline-offset-2 hover:underline dark:text-blue-400"
              >
                {kunde.name}
              </button>
            )}
          </div>
          {!dauerauftrag.aktiv && (
            <span className="border border-ind-line px-2 py-1 text-xs text-ind-ink-2">
              pausiert
            </span>
          )}
        </div>
        {dauerauftrag.beschreibung && (
          <p className="mt-2 text-sm text-ind-ink-2">{dauerauftrag.beschreibung}</p>
        )}

        <dl className="mt-3 space-y-1 text-sm">
          <div className="flex justify-between">
            <dt className="text-ind-ink-3">Intervall</dt>
            <dd className="text-ind-ink">
              {editIntervall === null ? (
                <span className="flex items-center gap-2">
                  alle {dauerauftrag.intervall_tage} Tage
                  {kannVerwalten && (
                    <button
                      onClick={() => setEditIntervall(String(dauerauftrag.intervall_tage))}
                      className="btn-touch text-xs text-blue-700 underline dark:text-blue-400"
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
                    className="w-16 border border-ind-line bg-transparent px-2 py-1 text-ind-ink"
                  />
                  Tage
                  <button
                    onClick={() => intervallMutation.mutate(Number(editIntervall))}
                    disabled={intervallMutation.isPending}
                    className="btn-touch rounded-md btn-industry btn-industry-primary px-2 py-1 text-xs disabled:opacity-50"
                  >
                    Speichern
                  </button>
                  <button
                    onClick={() => setEditIntervall(null)}
                    className="btn-touch text-xs text-slate-500 underline dark:text-stone-400"
                  >
                    Abbrechen
                  </button>
                </span>
              )}
            </dd>
          </div>
          {dauerauftrag.anzahl_ziele <= 1 && (
            <div className="flex justify-between">
              <dt className="text-ind-ink-3">Nächste Fälligkeit</dt>
              <dd className="text-ind-ink">{dauerauftrag.naechste_faelligkeit_am ?? "–"}</dd>
            </div>
          )}
          <div className="flex justify-between">
            <dt className="text-ind-ink-3">Modus</dt>
            <dd className="text-ind-ink">
              {dauerauftrag.modus === "rollierend"
                ? "Rollierend ab Abschluss"
                : "Fest ab geplantem Termin"}
            </dd>
          </div>
          {(dauerauftrag.toleranz_frueh_tage !== null || dauerauftrag.toleranz_spaet_tage !== null) && (
            <div className="flex justify-between">
              <dt className="text-ind-ink-3">Toleranz</dt>
              <dd className="text-ind-ink">
                {dauerauftrag.toleranz_frueh_tage !== null && `-${dauerauftrag.toleranz_frueh_tage} Tage`}
                {dauerauftrag.toleranz_frueh_tage !== null && dauerauftrag.toleranz_spaet_tage !== null && " / "}
                {dauerauftrag.toleranz_spaet_tage !== null && `+${dauerauftrag.toleranz_spaet_tage} Tage`}
              </dd>
            </div>
          )}
          <div className="flex justify-between">
            <dt className="text-ind-ink-3">Leistungstyp</dt>
            <dd className="text-ind-ink">{dauerauftrag.leistungstyp}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-ind-ink-3">Abrechnungsart</dt>
            <dd className="text-ind-ink">{dauerauftrag.abrechnungsart}</dd>
          </div>
        </dl>

        <div className="mt-4">
          <div className="mb-1 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ind-ink-3">
              Anlagen im Buendel ({dauerauftrag.anzahl_ziele})
            </h2>
            {kannVerwalten && !anlagenBearbeiten && (
              <button
                onClick={anlagenBearbeitenStarten}
                className="btn-touch text-xs text-blue-700 underline dark:text-blue-400"
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
                  className="flex items-center justify-between rounded-md bg-slate-50 px-2 py-1.5 text-sm dark:bg-stone-800/60"
                >
                  <span className="text-ind-ink-2">
                    {z.anlage_id ? anlageNameById.get(z.anlage_id) ?? "Anlage" : "Ohne Anlagenbezug"}
                  </span>
                  <span className="text-xs text-ind-ink-3">
                    {z.offener_vorgang_id ? (
                      <button
                        onClick={() => navigate(`/vorgaenge/${z.offener_vorgang_id}`)}
                        className="text-blue-700 underline dark:text-blue-400"
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
            <div className="space-y-2 rounded-md border border-slate-200 p-2 dark:border-stone-800">
              {!anlagenListe || anlagenListe.length === 0 ? (
                <p className="text-sm text-ind-ink-3">Keine Anlagen für diesen Kunden vorhanden.</p>
              ) : (
                <div className="max-h-48 space-y-1 overflow-y-auto">
                  {anlagenListe.map((a) => (
                    <label
                      key={a.id}
                      className="flex items-center gap-2 py-1 text-sm text-ind-ink-2"
                    >
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
                <label className="mb-1 block text-xs font-medium text-ind-ink-2">
                  Fälligkeit für neu hinzugefügte Anlagen
                </label>
                <input
                  type="date"
                  value={neueFaelligkeit}
                  onChange={(e) => setNeueFaelligkeit(e.target.value)}
                  className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
                />
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setAnlagenMutation.mutate()}
                  disabled={setAnlagenMutation.isPending}
                  className="btn-touch flex-1 rounded-md btn-industry btn-industry-primary py-2 text-sm font-medium disabled:opacity-50"
                >
                  Speichern
                </button>
                <button
                  onClick={() => setAnlagenBearbeiten(false)}
                  className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm text-slate-600 dark:border-stone-700 dark:text-stone-400"
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
              className="btn-touch w-full rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 disabled:opacity-50 dark:border-stone-700 dark:text-stone-300"
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
              className="btn-touch w-full rounded-md border border-red-300 py-2 text-sm font-medium text-red-700 disabled:opacity-50 dark:border-red-500/30 dark:text-red-400"
            >
              Dauer-Auftrag löschen
            </button>
          </div>
        )}
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold text-ind-ink-3">
          Verlauf ({dauerauftrag.vorgaenge.length} Vorgänge)
        </h2>
        {dauerauftrag.vorgaenge.length === 0 ? (
          <p className="text-sm text-ind-ink-3">Noch kein Vorgang erzeugt.</p>
        ) : (
          <div className="space-y-2">
            {dauerauftrag.vorgaenge.map((v) => (
              <button
                key={v.id}
                onClick={() => navigate(`/vorgaenge/${v.id}`)}
                className={`btn-touch flex w-full items-center justify-between border border-ind-line bg-ind-bg p-3 text-left ${
                  v.status === "storniert" ? "opacity-60 grayscale" : ""
                }`}
              >
                <div>
                  <div className="text-xs text-ind-ink-3">{v.vorgangsnummer}</div>
                  <div className="text-sm font-medium text-ind-ink">{v.titel}</div>
                </div>
                <span className={`px-2 py-1 text-xs font-semibold ${STATUS_BADGE[v.status]}`}>
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
