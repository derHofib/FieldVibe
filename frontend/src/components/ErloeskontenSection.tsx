import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BookOpen } from "lucide-react";
import { useState } from "react";

import { ApiError } from "../api/client";
import { mandantEinstellungenApi } from "../api/endpoints";
import type { MandantEinstellungen } from "../types";
import {
  ERLOESKONTO_ZEILEN,
  firmendatenMitKonten,
  kontenAusFirmendaten,
  kontenFehler,
  type ErloeskontoSchluessel,
} from "../utils/erloeskonten";
import { FehlerMeldung } from "./Hinweiskasten";

/** Erlöskonten je Steuerkategorie für den DATEV-Export (firmendaten.
 * buchhaltung.erloeskonten). Gesendet wird die vollständige Tabelle samt
 * allen übrigen Firmendaten, weil das Backend `buchhaltung` als Ganzes
 * ersetzt. */
export function ErloeskontenSection({ einstellungen }: { einstellungen: MandantEinstellungen }) {
  const queryClient = useQueryClient();
  const [konten, setKonten] = useState(() => kontenAusFirmendaten(einstellungen.firmendaten));
  const [besucht, setBesucht] = useState(false);
  const fehler = kontenFehler(konten);
  const hatFehler = Object.keys(fehler).length > 0;

  const speichernMutation = useMutation({
    mutationFn: () => mandantEinstellungenApi.firmendatenSpeichern(firmendatenMitKonten(einstellungen.firmendaten, konten)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mandant-einstellungen"] }),
  });

  function setzeFeld(schluessel: ErloeskontoSchluessel, feld: "konto" | "bu", wert: string) {
    setKonten({ ...konten, [schluessel]: { ...konten[schluessel], [feld]: wert } });
    speichernMutation.reset();
  }

  return (
    <div className="space-y-3 card-ap p-4" id="buchhaltung-erloeskonten">
      <div>
        <h2 className="flex items-center gap-1.5 text-sm font-semibold text-label">
          <BookOpen size={15} strokeWidth={2} className="text-tone-indigo" /> Buchhaltung – Erlöskonten
        </h2>
        <p className="mt-1 text-xs text-label2">
          Wird vom Steuerberater festgelegt. Für 19 % und 7 % gelten ohne Eintrag die Standardkonten 8400/8300. Für die
          übrigen Kategorien blockiert der DATEV-Export, bis ein Konto hinterlegt ist.
        </p>
      </div>

      <div className="divide-y-[0.5px] divide-sep">
        {ERLOESKONTO_ZEILEN.map((z) => {
          const f = fehler[z.schluessel];
          const kontoId = `konto-${z.schluessel}`;
          const buId = `bu-${z.schluessel}`;
          return (
            <div key={z.schluessel} className="grid grid-cols-[1fr_auto] items-start gap-x-3 gap-y-1 py-2.5 first:pt-0 last:pb-0 sm:grid-cols-[1fr_9rem_6rem]">
              <p className="col-span-2 self-center text-[15px] text-label sm:col-span-1">{z.label}</p>
              <div>
                <label htmlFor={kontoId} className="mb-0.5 block text-xs text-label2">
                  Konto
                </label>
                <input
                  id={kontoId}
                  value={konten[z.schluessel].konto}
                  onChange={(e) => setzeFeld(z.schluessel, "konto", e.target.value)}
                  onBlur={() => setBesucht(true)}
                  inputMode="numeric"
                  maxLength={8}
                  placeholder={z.standardKonto ?? "z. B. 8337"}
                  aria-invalid={!!f?.konto}
                  className="field-ap tabular-nums"
                />
              </div>
              <div className="w-24 sm:w-auto">
                <label htmlFor={buId} className="mb-0.5 block text-xs text-label2">
                  BU-Schlüssel
                </label>
                <input
                  id={buId}
                  value={konten[z.schluessel].bu}
                  onChange={(e) => setzeFeld(z.schluessel, "bu", e.target.value)}
                  onBlur={() => setBesucht(true)}
                  inputMode="numeric"
                  maxLength={3}
                  aria-invalid={!!f?.bu}
                  className="field-ap tabular-nums"
                />
              </div>
              {besucht && f && (
                <p role="alert" className="col-span-2 text-xs text-st-fehlt sm:col-span-3">
                  {[f.konto, f.bu].filter(Boolean).join(" · ")}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {speichernMutation.isError && (
        <FehlerMeldung
          alsKasten
          meldung={
            speichernMutation.error instanceof ApiError
              ? speichernMutation.error.message
              : "Erlöskonten konnten nicht gespeichert werden"
          }
        />
      )}

      <div className="flex items-center gap-2">
        <button
          onClick={() => speichernMutation.mutate()}
          disabled={speichernMutation.isPending || hatFehler}
          className="btn-touch rounded-md btn-ap-primary px-3 py-1.5 text-sm font-medium disabled:opacity-50"
        >
          Speichern
        </button>
        {speichernMutation.isSuccess && <span className="text-xs text-st-erledigt">Gespeichert.</span>}
      </div>
    </div>
  );
}
