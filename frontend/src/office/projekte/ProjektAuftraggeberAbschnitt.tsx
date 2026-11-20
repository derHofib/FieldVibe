import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../../api/client";
import { kundenApi, projekteApi, standorteApi } from "../../api/endpoints";
import { Select } from "../../components/apple/Select";
import { FehlerMeldung } from "../../components/Hinweiskasten";
import { SearchableSelect } from "../../components/SearchableSelect";
import { ABSCHNITT_AKTION, Abschnitt } from "../../pages/feld/vorgang/Abschnitt";
import type { Projekt } from "../../types";

/** Abschnitt "Auftraggeber & Baustelle" im Projekt: Kunde (Voraussetzung für Kontakte vor Ort) und Standort. */
export function ProjektAuftraggeberAbschnitt({ projekt }: { projekt: Projekt }) {
  const queryClient = useQueryClient();
  const [bearbeiten, setBearbeiten] = useState(false);
  const [kundeId, setKundeId] = useState("");
  const [standortId, setStandortId] = useState("");

  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list(), enabled: bearbeiten });
  const { data: standorte } = useQuery({
    queryKey: ["standorte", kundeId, "aktiv"],
    queryFn: () => standorteApi.list(kundeId, true),
    enabled: bearbeiten && !!kundeId,
  });

  const speichern = useMutation({
    meta: { erfolg: "Gespeichert" },
    mutationFn: () => projekteApi.update(projekt.id, { kunde_id: kundeId || null, standort_id: kundeId ? standortId || null : null }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["projekte"] });
      void queryClient.invalidateQueries({ queryKey: ["vor-ort"] });
      setBearbeiten(false);
    },
  });

  return (
    <Abschnitt
      titel="Auftraggeber & Baustelle"
      aktion={
        !bearbeiten ? (
          <button
            type="button"
            onClick={() => {
              setKundeId(projekt.kunde_id ?? "");
              setStandortId(projekt.standort_id ?? "");
              speichern.reset();
              setBearbeiten(true);
            }}
            className={ABSCHNITT_AKTION}
          >
            Bearbeiten
          </button>
        ) : undefined
      }
    >
      {bearbeiten ? (
        <div className="space-y-2">
          <div>
            <span className="mb-1 block text-sekundaer text-label2">Auftraggeber</span>
            <SearchableSelect
              value={kundeId}
              onChange={(v) => {
                setKundeId(v);
                // Standort gehört zum Kunden: bei Wechsel zurücksetzen statt einen 422 zu provozieren.
                setStandortId("");
              }}
              placeholder="Kein Auftraggeber"
              options={[{ value: "", label: "Kein Auftraggeber" }, ...(kunden ?? []).map((k) => ({ value: k.id, label: k.name }))]}
            />
          </div>
          {kundeId && (
            <label className="block text-sekundaer text-label2">
              Standort
              <Select className="mt-1 w-full" value={standortId} onChange={(e) => setStandortId(e.target.value)}>
                <option value="">Kein Standort</option>
                {(standorte ?? []).map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.bezeichnung}
                  </option>
                ))}
              </Select>
            </label>
          )}
          {speichern.isError && (
            <FehlerMeldung alsKasten meldung={speichern.error instanceof ApiError ? speichern.error.message : "Speichern fehlgeschlagen."} />
          )}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setBearbeiten(false)} className="btn-touch btn-ap px-3 text-sekundaer">
              Abbrechen
            </button>
            <button
              type="button"
              disabled={speichern.isPending}
              onClick={() => speichern.mutate()}
              className="btn-touch btn-ap-primary px-3 text-sekundaer"
            >
              Speichern
            </button>
          </div>
        </div>
      ) : (
        <dl className="space-y-1.5 text-fliess">
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-label2">Auftraggeber</dt>
            <dd className="text-right font-medium text-label">{projekt.kunde_name ?? (projekt.kunde_id ? "…" : "—")}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-label2">Standort</dt>
            <dd className="text-right font-medium text-label">{projekt.standort_bezeichnung ?? (projekt.standort_id ? "…" : "—")}</dd>
          </div>
        </dl>
      )}
    </Abschnitt>
  );
}
