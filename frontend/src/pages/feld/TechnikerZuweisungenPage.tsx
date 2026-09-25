import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { anlagenApi, fahrzeugZuweisungenApi, technikerZuweisungenApi } from "../../api/endpoints";

function FahrzeugAuswahl({ userId, aktuellesFahrzeugId }: { userId: string; aktuellesFahrzeugId: string | null }) {
  const queryClient = useQueryClient();
  const { data: fahrzeuge } = useQuery({
    queryKey: ["lagerorte", "fahrzeug"],
    queryFn: () => anlagenApi.list(undefined, "fahrzeug"),
  });

  const setzenMutation = useMutation({
    mutationFn: (anlageId: string | null) => fahrzeugZuweisungenApi.setzen(userId, anlageId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["fahrzeug-zuweisungen"] }),
  });

  return (
    <select
      value={aktuellesFahrzeugId ?? ""}
      onChange={(e) => setzenMutation.mutate(e.target.value || null)}
      disabled={setzenMutation.isPending}
      className="btn-touch mt-2 w-full border border-sep bg-transparent px-2 py-1.5 text-sm disabled:opacity-50 text-label"
    >
      <option value="">Kein Fahrzeug</option>
      {(fahrzeuge ?? []).map((f) => (
        <option key={f.id} value={f.id}>
          {f.bezeichnung}
        </option>
      ))}
    </select>
  );
}

export function TechnikerZuweisungenPage() {
  const navigate = useNavigate();
  const { data: uebersicht, isLoading } = useQuery({
    queryKey: ["techniker-zuweisungen"],
    queryFn: technikerZuweisungenApi.uebersicht,
  });
  const { data: fahrzeugUebersicht } = useQuery({
    queryKey: ["fahrzeug-zuweisungen"],
    queryFn: fahrzeugZuweisungenApi.uebersicht,
  });
  const fahrzeugByTechnikerId = new Map(
    (fahrzeugUebersicht ?? []).map((row) => [row.techniker.id, row.fahrzeug])
  );

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-label">Techniker-Zuweisungen</h1>
      <p className="text-sm text-label2">
        Welcher Techniker betreut welche Kunden und faehrt welches Fahrzeug. Kunden zuweisen/ändern
        geht über das Kunden-Profil, das Fahrzeug direkt hier.
      </p>

      {isLoading ? (
        <p className="text-center text-label2">Lädt…</p>
      ) : !uebersicht || uebersicht.length === 0 ? (
        <p className="text-sm text-label2">Keine Techniker in diesem Mandanten angelegt.</p>
      ) : (
        <div className="space-y-3">
          {uebersicht.map((row) => (
            <div
              key={row.techniker.id}
              className="border border-sep bg-card p-4"
            >
              <div className="font-semibold text-label">{row.techniker.name}</div>
              <div className="text-xs text-label2">{row.techniker.email}</div>
              {row.kunden.length === 0 ? (
                <p className="mt-2 text-sm text-label2">Kein Kunde zugewiesen.</p>
              ) : (
                <div className="mt-2 flex flex-wrap gap-1">
                  {row.kunden.map((k) => (
                    <button
                      key={k.id}
                      onClick={() => navigate(`/kunden/${k.id}`)}
                      className="btn-touch border border-sep px-2 py-0.5 text-xs text-label"
                    >
                      {k.name}
                    </button>
                  ))}
                </div>
              )}
              <div className="mt-2 border-t border-sep pt-2 ">
                <label className="mb-1 block text-xs text-label2">Fahrzeug</label>
                <FahrzeugAuswahl
                  userId={row.techniker.id}
                  aktuellesFahrzeugId={fahrzeugByTechnikerId.get(row.techniker.id)?.id ?? null}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
