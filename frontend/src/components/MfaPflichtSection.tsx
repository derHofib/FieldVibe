import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";

import { ApiError } from "../api/client";
import { mandantEinstellungenApi } from "../api/endpoints";
import type { MandantEinstellungen } from "../types";
import { Switch } from "./apple/Switch";
import { Hinweiskasten } from "./Hinweiskasten";

/** Sicherheit: Zwei-Faktor-Anmeldung für alle Mitarbeiter vorschreiben
 * (firmendaten.mfa_pflicht, Standard aus). */
export function MfaPflichtSection({ einstellungen }: { einstellungen: MandantEinstellungen }) {
  const queryClient = useQueryClient();
  const an = einstellungen.firmendaten.mfa_pflicht === true;

  const speichern = useMutation({
    mutationFn: (wert: boolean) => mandantEinstellungenApi.firmendatenSpeichern({ mfa_pflicht: wert }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mandant-einstellungen"] }),
  });

  return (
    <div className="space-y-3 card-ap p-4" id="sicherheit-mfa">
      <h2 className="flex items-center gap-1.5 text-sm font-semibold text-label">
        <ShieldCheck size={15} strokeWidth={2} className="text-tone-emerald" aria-hidden="true" /> Sicherheit
      </h2>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p id="mfa-pflicht-label" className="text-sm font-medium text-label">
            Zwei-Faktor-Anmeldung vorschreiben
          </p>
          <p className="text-xs text-label2">
            Alle Mitarbeiter müssen beim nächsten Anmelden eine Authenticator-App einrichten, bevor sie die App
            nutzen können. Bereits angemeldete Sitzungen laufen bis zum nächsten Token-Refresh weiter.
          </p>
        </div>
        <Switch checked={an} onChange={(w) => speichern.mutate(w)} ariaLabel="Zwei-Faktor-Anmeldung vorschreiben" />
      </div>
      {speichern.isError && (
        <Hinweiskasten ton="fehler">
          {speichern.error instanceof ApiError ? speichern.error.message : "Speichern fehlgeschlagen"}
        </Hinweiskasten>
      )}
    </div>
  );
}
