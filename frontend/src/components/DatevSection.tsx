import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet } from "lucide-react";
import { useState } from "react";

import { ApiError } from "../api/client";
import { mandantEinstellungenApi } from "../api/endpoints";
import type { MandantEinstellungen } from "../types";
import {
  KONTENRAHMEN,
  MONATE,
  datevAusFirmendaten,
  datevFehler,
  firmendatenMitDatev,
  type DatevEingabe,
} from "../utils/datev";
import { FehlerMeldung, Hinweiskasten } from "./Hinweiskasten";

/** DATEV-Stammdaten (firmendaten.buchhaltung): Header des Buchungsstapels.
 * Gesendet wird `buchhaltung` samt den Erlöskonten, weil das Backend es als
 * Ganzes ersetzt. */
export function DatevSection({ einstellungen }: { einstellungen: MandantEinstellungen }) {
  const queryClient = useQueryClient();
  const [eingabe, setEingabe] = useState<DatevEingabe>(() => datevAusFirmendaten(einstellungen.firmendaten));
  const [besucht, setBesucht] = useState(false);
  const fehler = datevFehler(eingabe);
  const hatFehler = Object.keys(fehler).length > 0;
  const gespeicherteLaenge = einstellungen.firmendaten.buchhaltung?.sachkontenlaenge ?? 4;
  const laengeGeaendert = Number(eingabe.sachkontenlaenge) !== gespeicherteLaenge;

  const speichernMutation = useMutation({
    mutationFn: () => mandantEinstellungenApi.firmendatenSpeichern(firmendatenMitDatev(einstellungen.firmendaten, eingabe)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mandant-einstellungen"] }),
  });

  function setzeFeld<K extends keyof DatevEingabe>(feld: K, wert: DatevEingabe[K]) {
    setEingabe({ ...eingabe, [feld]: wert });
    speichernMutation.reset();
  }

  return (
    <div className="space-y-3 card-ap p-4" id="buchhaltung-datev">
      <div>
        <h2 className="flex items-center gap-1.5 text-sm font-semibold text-label">
          <FileSpreadsheet size={15} strokeWidth={2} className="text-tone-indigo" /> DATEV / Buchhaltung
        </h2>
        <p className="mt-1 text-xs text-label2">
          Stammdaten für den DATEV-Export (Buchungsstapel). Die Werte kennt der Steuerberater – ohne Berater- und
          Mandantennummer lässt sich der Export nicht erzeugen.
        </p>
      </div>

      <Hinweiskasten ton="info" titel="Vor dem ersten Import abstimmen">
        <p>Vor dem ersten Import mit dem Steuerberater abstimmen (Testimport), insbesondere Kontenrahmen und Sachkontenlänge.</p>
      </Hinweiskasten>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="datev-berater" className="mb-0.5 block text-xs text-label2">
            Beraternummer
          </label>
          <input
            id="datev-berater"
            value={eingabe.beraterNr}
            onChange={(e) => setzeFeld("beraterNr", e.target.value)}
            onBlur={() => setBesucht(true)}
            inputMode="numeric"
            maxLength={7}
            placeholder="1001 bis 9999999"
            aria-invalid={!!fehler.beraterNr}
            className="field-ap tabular-nums"
          />
        </div>
        <div>
          <label htmlFor="datev-mandant" className="mb-0.5 block text-xs text-label2">
            Mandantennummer
          </label>
          <input
            id="datev-mandant"
            value={eingabe.mandantNr}
            onChange={(e) => setzeFeld("mandantNr", e.target.value)}
            onBlur={() => setBesucht(true)}
            inputMode="numeric"
            maxLength={5}
            placeholder="1 bis 99999"
            aria-invalid={!!fehler.mandantNr}
            className="field-ap tabular-nums"
          />
        </div>
        <div>
          <label htmlFor="datev-wj" className="mb-0.5 block text-xs text-label2">
            Wirtschaftsjahr beginnt im
          </label>
          <select
            id="datev-wj"
            value={eingabe.wjBeginnMonat}
            onChange={(e) => setzeFeld("wjBeginnMonat", e.target.value)}
            className="field-ap"
          >
            {MONATE.map((name, i) => (
              <option key={name} value={i + 1}>
                {name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="datev-skr" className="mb-0.5 block text-xs text-label2">
            Kontenrahmen
          </label>
          <select
            id="datev-skr"
            value={eingabe.kontenrahmen}
            onChange={(e) => setzeFeld("kontenrahmen", e.target.value as DatevEingabe["kontenrahmen"])}
            className="field-ap"
          >
            {KONTENRAHMEN.map((skr) => (
              <option key={skr} value={skr}>
                {skr}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="datev-laenge" className="mb-0.5 block text-xs text-label2">
            Sachkontenlänge
          </label>
          <input
            id="datev-laenge"
            value={eingabe.sachkontenlaenge}
            onChange={(e) => setzeFeld("sachkontenlaenge", e.target.value)}
            onBlur={() => setBesucht(true)}
            inputMode="numeric"
            maxLength={1}
            placeholder="4 bis 8"
            aria-invalid={!!fehler.sachkontenlaenge}
            className="field-ap tabular-nums"
          />
          <p className="mt-0.5 text-xs text-label2">
            Personenkonten (Debitoren/Kreditoren) haben eine Stelle mehr, z. B. 5 Stellen bei 4.
          </p>
        </div>
      </div>

      {besucht && hatFehler && (
        <p role="alert" className="text-xs text-st-fehlt">
          {Object.values(fehler).join(" · ")}
        </p>
      )}

      {laengeGeaendert && (
        <p className="text-xs text-label2">
          Bereits vergebene Debitoren-/Kreditorenkonten behalten ihre Länge und müssen nach einer Änderung der
          Sachkontenlänge angepasst werden, sonst blockiert der Export.
        </p>
      )}

      {speichernMutation.isError && (
        <FehlerMeldung
          alsKasten
          meldung={
            speichernMutation.error instanceof ApiError
              ? speichernMutation.error.message
              : "DATEV-Stammdaten konnten nicht gespeichert werden"
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
