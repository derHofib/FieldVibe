import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../api/client";
import { anlagenApi, fahrzeugZuweisungenApi } from "../api/endpoints";
import { Select } from "./apple/Select";
import { Sheet } from "./apple/Sheet";
import { FehlerMeldung } from "./Hinweiskasten";

/** Fahrzeug eines Mitarbeiters setzen -- vormals auf der Seite "Techniker-Zuweisungen". */
export function FahrzeugZuordnungSheet({
  userId,
  name,
  aktuellesFahrzeugId,
  onClose,
}: {
  userId: string;
  name: string;
  aktuellesFahrzeugId: string | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [fahrzeugId, setFahrzeugId] = useState(aktuellesFahrzeugId ?? "");
  const { data: fahrzeuge } = useQuery({
    queryKey: ["lagerorte", "fahrzeug"],
    queryFn: () => anlagenApi.list(undefined, "fahrzeug"),
  });

  const speichern = useMutation({
    meta: { erfolg: "Fahrzeug gespeichert" },
    mutationFn: () => fahrzeugZuweisungenApi.setzen(userId, fahrzeugId || null),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["fahrzeug-zuweisungen"] });
      onClose();
    },
  });

  return (
    <Sheet
      offen
      onClose={onClose}
      titel="Fahrzeug"
      links={
        <button type="button" onClick={onClose} className="text-zeile text-tint-text">
          Abbrechen
        </button>
      }
      rechts={
        <button
          type="button"
          onClick={() => speichern.mutate()}
          disabled={speichern.isPending}
          className="text-zeile font-semibold text-tint-text disabled:opacity-50"
        >
          Speichern
        </button>
      }
    >
      <div className="space-y-3 p-4">
        <label htmlFor="account-fahrzeug" className="block text-fliess font-medium text-label">
          Fahrzeug von {name}
        </label>
        <Select id="account-fahrzeug" value={fahrzeugId} onChange={(e) => setFahrzeugId(e.target.value)} disabled={speichern.isPending}>
          <option value="">Kein Fahrzeug</option>
          {(fahrzeuge ?? []).map((f) => (
            <option key={f.id} value={f.id}>
              {f.bezeichnung}
            </option>
          ))}
        </Select>
        {speichern.isError && (
          <FehlerMeldung
            alsKasten
            meldung={speichern.error instanceof ApiError ? speichern.error.message : "Speichern fehlgeschlagen"}
          />
        )}
      </div>
    </Sheet>
  );
}
