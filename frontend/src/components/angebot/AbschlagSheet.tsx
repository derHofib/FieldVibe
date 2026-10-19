import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { ApiError } from "../../api/client";
import { rechnungenApi } from "../../api/endpoints";
import type { Rechnung } from "../../types";
import { formatEuro } from "../../utils/format";
import { abschlagPayload, abschlagVorschau, type AbschlagModus } from "../../utils/rechnungsart";
import { SegmentedControl } from "../apple/SegmentedControl";
import { Sheet } from "../apple/Sheet";
import { FehlerMeldung } from "../Hinweiskasten";

const FORM_ID = "abschlag-formular";

const MODUS_OPTIONEN: { wert: AbschlagModus; label: string }[] = [
  { wert: "prozent", label: "Prozent" },
  { wert: "netto", label: "Nettobetrag" },
];

/** Abschlagsrechnung zu einem angenommenen Angebot anlegen (immer als Entwurf).
 * Die 100-%-Grenze prüft der Server verbindlich; die Vorschau hier verhindert
 * nur den offensichtlichen Fehlversuch. */
export function AbschlagSheet({
  angebotId,
  angebotNetto,
  restNetto,
  onClose,
  onErstellt,
}: {
  angebotId: string;
  angebotNetto: string;
  restNetto: string;
  onClose: () => void;
  onErstellt: (rechnung: Rechnung) => void;
}) {
  const queryClient = useQueryClient();
  const [modus, setModus] = useState<AbschlagModus>("prozent");
  const [eingabe, setEingabe] = useState("");
  const [faelligAm, setFaelligAm] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);

  const vorschau = abschlagVorschau(modus, eingabe, angebotNetto, restNetto);
  const gueltig = !!eingabe.trim() && vorschau.betrag !== null && !vorschau.fehler;

  const erstellen = useMutation({
    mutationFn: () => rechnungenApi.ausAngebot(abschlagPayload(angebotId, modus, eingabe, faelligAm)),
    onSuccess: (rechnung) => {
      queryClient.invalidateQueries({ queryKey: ["angebot", angebotId] });
      queryClient.invalidateQueries({ queryKey: ["angebote"] });
      queryClient.invalidateQueries({ queryKey: ["rechnungen"] });
      queryClient.invalidateQueries({ queryKey: ["rechnungen-uebersicht"] });
      onErstellt(rechnung);
    },
    onError: (err) =>
      setFehler(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen."),
  });

  function absenden(e: FormEvent) {
    e.preventDefault();
    if (!gueltig || erstellen.isPending) return;
    setFehler(null);
    erstellen.mutate();
  }

  return (
    <Sheet
      offen
      onClose={onClose}
      titel="Abschlag erstellen"
      links={
        <button type="button" onClick={onClose} className="text-[17px] text-tint-text">
          Abbrechen
        </button>
      }
      rechts={
        <button
          type="submit"
          form={FORM_ID}
          disabled={!gueltig || erstellen.isPending}
          className="text-[17px] font-semibold text-tint-text disabled:opacity-40"
        >
          Erstellen
        </button>
      }
    >
      <form id={FORM_ID} onSubmit={absenden} className="space-y-4 p-4">
        {fehler && <FehlerMeldung meldung={fehler} alsKasten />}

        <SegmentedControl
          ariaLabel="Abschlag berechnen als"
          optionen={MODUS_OPTIONEN}
          wert={modus}
          onChange={(neu) => {
            setModus(neu);
            setEingabe("");
          }}
          groesse="mobil"
          volleBreite
        />

        <div>
          <label htmlFor="abschlag-eingabe" className="mb-1 block text-xs font-medium text-label2">
            {modus === "prozent" ? "Anteil am Angebot (%)" : "Nettobetrag (EUR)"}
          </label>
          <input
            id="abschlag-eingabe"
            type="text"
            inputMode="decimal"
            autoComplete="off"
            value={eingabe}
            onChange={(e) => setEingabe(e.target.value)}
            placeholder={modus === "prozent" ? "z. B. 30" : "z. B. 1500,00"}
            aria-invalid={!!vorschau.fehler}
            aria-describedby="abschlag-vorschau"
            className="field-ap tabular-nums"
          />
        </div>

        <div id="abschlag-vorschau" className="card-ap space-y-1 p-3 text-sm">
          <div className="flex justify-between text-label2">
            <span>Angebot netto</span>
            <span className="tabular-nums">{formatEuro(angebotNetto)}</span>
          </div>
          <div className="flex justify-between font-semibold text-label">
            <span>Dieser Abschlag (netto)</span>
            <span className="tabular-nums">{vorschau.betrag !== null ? formatEuro(vorschau.betrag) : "—"}</span>
          </div>
          <div className="flex justify-between text-label2">
            <span>Rest danach</span>
            <span className="tabular-nums">
              {vorschau.restNachher !== null && !vorschau.fehler ? formatEuro(vorschau.restNachher) : "—"}
            </span>
          </div>
          {vorschau.fehler && (
            <p role="alert" className="pt-1 text-xs text-st-fehlt">
              {vorschau.fehler}
            </p>
          )}
        </div>

        <div>
          <label htmlFor="abschlag-faellig" className="mb-1 block text-xs font-medium text-label2">
            Fällig am (optional)
          </label>
          <input
            id="abschlag-faellig"
            type="date"
            value={faelligAm}
            onChange={(e) => setFaelligAm(e.target.value)}
            className="field-ap"
          />
        </div>

        <p className="text-xs text-label2">
          Der Abschlag wird als Entwurf angelegt und kann vor dem Versand noch geprüft werden.
        </p>
      </form>
    </Sheet>
  );
}
