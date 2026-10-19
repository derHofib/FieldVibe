import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { ApiError } from "../../api/client";
import { angeboteApi } from "../../api/endpoints";
import { heuteIso } from "../../utils/format";
import { Sheet } from "../apple/Sheet";
import { FehlerMeldung } from "../Hinweiskasten";

const FORM_ID = "angebot-gueltigkeit-formular";

/** Gültigkeit eines Angebots setzen bzw. verlängern -- der Weg, ein
 * abgelaufenes (noch versendetes) Angebot wieder annehmbar zu machen. */
export function GueltigkeitSheet({
  angebotId,
  aktuell,
  onClose,
}: {
  angebotId: string;
  aktuell: string | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const heute = heuteIso();
  // Vorbelegung: 14 Tage ab heute, wenn das Datum schon vorbei ist oder fehlt.
  const [datum, setDatum] = useState(aktuell && aktuell >= heute ? aktuell : heuteIso(14));
  const [fehler, setFehler] = useState<string | null>(null);

  const speichern = useMutation({
    mutationFn: () => angeboteApi.update(angebotId, { gueltig_bis: datum }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["angebot", angebotId] });
      queryClient.invalidateQueries({ queryKey: ["angebote"] });
      onClose();
    },
    onError: (err) =>
      setFehler(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen."),
  });

  function absenden(e: FormEvent) {
    e.preventDefault();
    if (!datum) {
      setFehler("Bitte ein Datum wählen");
      return;
    }
    setFehler(null);
    speichern.mutate();
  }

  return (
    <Sheet
      offen
      onClose={onClose}
      titel="Gültigkeit verlängern"
      links={
        <button type="button" onClick={onClose} className="text-[17px] text-tint">
          Abbrechen
        </button>
      }
      rechts={
        <button
          type="submit"
          form={FORM_ID}
          disabled={speichern.isPending}
          className="text-[17px] font-semibold text-tint disabled:opacity-40"
        >
          Speichern
        </button>
      }
    >
      <form id={FORM_ID} onSubmit={absenden} className="space-y-4 p-4">
        {fehler && <FehlerMeldung meldung={fehler} alsKasten />}
        <div>
          <label htmlFor="angebot-gueltig-bis" className="mb-1 block text-xs font-medium text-label2">
            Gültig bis
          </label>
          <input
            id="angebot-gueltig-bis"
            type="date"
            value={datum}
            min={heute}
            onChange={(e) => setDatum(e.target.value)}
            className="field-ap"
            required
          />
        </div>
      </form>
    </Sheet>
  );
}
