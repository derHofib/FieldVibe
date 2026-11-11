import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { anlagenApi, fahrzeugZuweisungenApi, technikerZuweisungenApi } from "../../api/endpoints";
import { FehlerZustand } from "../../components/FehlerZustand";
import { SkeletonList } from "../../components/Skeleton";
import { Select } from "../../components/apple/Select";

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
    <Select
      className="mt-2"
      value={aktuellesFahrzeugId ?? ""}
      onChange={(e) => setzenMutation.mutate(e.target.value || null)}
      disabled={setzenMutation.isPending}
    >
      <option value="">Kein Fahrzeug</option>
      {(fahrzeuge ?? []).map((f) => (
        <option key={f.id} value={f.id}>
          {f.bezeichnung}
        </option>
      ))}
    </Select>
  );
}

export function TechnikerZuweisungenPage() {
  const navigate = useNavigate();
  const { data: uebersicht, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
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
      <h1 className="text-titel-mobil font-bold text-label">Techniker-Zuweisungen</h1>
      <p className="text-sekundaer text-label2">
        Welcher Techniker betreut welche Kunden und fährt welches Fahrzeug. Kunden zuweisen/ändern
        geht über das Kunden-Profil, das Fahrzeug direkt hier.
      </p>

      {isLoading ? (
        <SkeletonList count={4} />
      ) : ladeFehler && !uebersicht ? (
        <FehlerZustand fehler={ladeFehler} was="Die Techniker" onErneut={() => void neuLaden()} />
      ) : !uebersicht || uebersicht.length === 0 ? (
        <p className="text-sekundaer text-label2">Keine Techniker in diesem Mandanten angelegt.</p>
      ) : (
        <div className="space-y-3">
          {uebersicht.map((row) => (
            <div
              key={row.techniker.id}
              className="card-ap p-4"
            >
              <div className="font-semibold text-label">{row.techniker.name}</div>
              <div className="text-sekundaer text-label2">{row.techniker.email}</div>
              {row.kunden.length === 0 ? (
                <p className="mt-2 text-sekundaer text-label2">Kein Kunde zugewiesen.</p>
              ) : (
                <div className="mt-2 flex flex-wrap gap-1">
                  {row.kunden.map((k) => (
                    <button
                      key={k.id}
                      onClick={() => navigate(`/kunden/${k.id}`)}
                      className="btn-touch border rounded-[var(--radius-ap-md)] border-sep px-2 py-0.5 text-meta text-label"
                    >
                      {k.name}
                    </button>
                  ))}
                </div>
              )}
              <div className="mt-2 border-t border-sep pt-2 ">
                <label className="mb-1 block text-sekundaer text-label2">Fahrzeug</label>
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
