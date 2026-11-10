import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Scale } from "lucide-react";
import { useState } from "react";

import { ApiError } from "../api/client";
import { mandantEinstellungenApi } from "../api/endpoints";
import type { MandantEinstellungen } from "../types";
import {
  MODUS_OPTIONEN,
  firmendatenAusFormular,
  formularAusFirmendaten,
  portalFormularFehler,
  zeigtPlatzhalterBelehrung,
  type PortalFormular,
} from "../utils/verbraucherschutz";
import { FehlerMeldung, Hinweiskasten } from "./Hinweiskasten";

/** Kundenportal / Verbraucherschutz: B2C-Schalter, Widerrufsbelehrung und
 * Barrierefreiheits-Kontakt (firmendaten.portal_verbraucherschutz usw.). */
export function PortalVerbraucherschutzSection({ einstellungen }: { einstellungen: MandantEinstellungen }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<PortalFormular>(() => formularAusFirmendaten(einstellungen.firmendaten));
  const fehler = portalFormularFehler(form);
  const hatFehler = Object.keys(fehler).length > 0;

  const speichernMutation = useMutation({
    mutationFn: () => mandantEinstellungenApi.firmendatenSpeichern(firmendatenAusFormular(form)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mandant-einstellungen"] }),
  });

  function setze<K extends keyof PortalFormular>(feld: K, wert: PortalFormular[K]) {
    setForm({ ...form, [feld]: wert });
    speichernMutation.reset();
  }

  return (
    <div className="space-y-3 card-ap p-4" id="kundenportal-verbraucherschutz">
      <div>
        <h2 className="flex items-center gap-1.5 text-sm font-semibold text-label">
          <Scale size={15} strokeWidth={2} className="text-tone-violet" aria-hidden="true" /> Kundenportal /
          Verbraucherschutz
        </h2>
        <p className="mt-1 text-xs text-label2">
          Regelt, wie Privatkunden Angebote im Portal beauftragen und widerrufen können.
        </p>
      </div>

      <Hinweiskasten ton="warnung" titel="Rechtlich prüfen lassen">
        Die hier angezeigten Muster- und Platzhaltertexte ersetzen keine Rechtsberatung. Lassen Sie
        Widerrufsbelehrung, Widerrufsformular und die Barrierefreiheitserklärung von Ihrer Rechtsberatung prüfen,
        bevor Sie den Verbraucherschutz einsetzen.
      </Hinweiskasten>

      <fieldset className="space-y-2">
        <legend className="mb-1 text-sm font-medium text-label">B2C-Ablauf im Portal</legend>
        {MODUS_OPTIONEN.map((o) => (
          <label key={o.wert} className="flex items-start gap-2 text-sm text-label">
            <input
              type="radio"
              name="portal-verbraucherschutz"
              checked={form.modus === o.wert}
              onChange={() => setze("modus", o.wert)}
              className="mt-0.5"
            />
            <span>
              {o.label}
              <span className="block text-xs text-label2">{o.hinweis}</span>
            </span>
          </label>
        ))}
        <p className="text-xs text-label2">
          Bestandsmandanten ohne Einstellung stehen auf „Aus“; neue Mandanten starten mit „Nur für Privatkunden“.
        </p>
      </fieldset>

      {zeigtPlatzhalterBelehrung(form.modus, form.belehrungText) && (
        <Hinweiskasten ton="warnung" titel="Keine eigene Widerrufsbelehrung hinterlegt">
          Privatkunden sehen derzeit einen mit „Platzhalter – von Rechtsberatung prüfen“ gekennzeichneten Mustertext.
          Beauftragungen sind trotzdem möglich.
        </Hinweiskasten>
      )}

      <div>
        <label htmlFor="portal-belehrung-text" className="mb-0.5 block text-sm font-medium text-label">
          Widerrufsbelehrung
        </label>
        <textarea
          id="portal-belehrung-text"
          value={form.belehrungText}
          onChange={(e) => setze("belehrungText", e.target.value)}
          rows={10}
          aria-invalid={!!fehler.belehrungText}
          aria-describedby="portal-belehrung-hinweis"
          className="field-ap"
        />
        <p id="portal-belehrung-hinweis" className="mt-0.5 text-xs text-label2">
          Reiner Text, Absätze durch Leerzeilen trennen (kein Markdown). Leer lassen für den Platzhalter-Mustertext.
        </p>
        {fehler.belehrungText && <FehlerMeldung meldung={fehler.belehrungText} />}
      </div>

      <div>
        <label htmlFor="portal-belehrung-version" className="mb-0.5 block text-sm font-medium text-label">
          Version / Stand der Belehrung
        </label>
        <input
          id="portal-belehrung-version"
          value={form.belehrungVersion}
          onChange={(e) => setze("belehrungVersion", e.target.value)}
          maxLength={60}
          placeholder="z. B. 2026-10-19"
          aria-describedby="portal-belehrung-version-hinweis"
          className="field-ap"
        />
        <p id="portal-belehrung-version-hinweis" className="mt-0.5 text-xs text-label2">
          Wird im Annahmenachweis gespeichert. Bei jeder Textänderung neu setzen.
        </p>
      </div>

      <div className="space-y-2 border-t-[0.5px] border-sep pt-3">
        <h3 className="text-sm font-medium text-label">Barrierefreiheitserklärung</h3>
        <div>
          <label htmlFor="portal-bf-email" className="mb-0.5 block text-xs text-label2">
            Kontakt für Feedback (E-Mail)
          </label>
          <input
            id="portal-bf-email"
            type="email"
            value={form.barrierefreiheitEmail}
            onChange={(e) => setze("barrierefreiheitEmail", e.target.value)}
            aria-invalid={!!fehler.barrierefreiheitEmail}
            className="field-ap"
          />
          {fehler.barrierefreiheitEmail && <FehlerMeldung meldung={fehler.barrierefreiheitEmail} />}
        </div>
        <div>
          <label htmlFor="portal-bf-stand" className="mb-0.5 block text-xs text-label2">
            Stand der Erklärung
          </label>
          <input
            id="portal-bf-stand"
            type="date"
            value={form.barrierefreiheitStand}
            onChange={(e) => setze("barrierefreiheitStand", e.target.value)}
            className="field-ap"
          />
        </div>
        <div>
          <label htmlFor="portal-bf-url" className="mb-0.5 block text-xs text-label2">
            Eigene Erklärung (URL, optional – ersetzt die Platzhalter-Seite)
          </label>
          <input
            id="portal-bf-url"
            type="url"
            value={form.barrierefreiheitUrl}
            onChange={(e) => setze("barrierefreiheitUrl", e.target.value)}
            aria-invalid={!!fehler.barrierefreiheitUrl}
            className="field-ap"
          />
          {fehler.barrierefreiheitUrl && <FehlerMeldung meldung={fehler.barrierefreiheitUrl} />}
        </div>
      </div>

      {speichernMutation.isError && (
        <FehlerMeldung
          meldung={speichernMutation.error instanceof ApiError ? speichernMutation.error.message : "Speichern fehlgeschlagen"}
        />
      )}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => speichernMutation.mutate()}
          disabled={speichernMutation.isPending || hatFehler}
          className="btn-touch rounded-md btn-ap-primary px-3 py-1.5 text-sm font-medium disabled:opacity-50"
        >
          Speichern
        </button>
        {speichernMutation.isSuccess && (
          <span role="status" className="text-xs text-st-erledigt ">
            Gespeichert.
          </span>
        )}
      </div>
    </div>
  );
}
