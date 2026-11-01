import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { ApiError } from "../../api/client";
import { angeboteApi } from "../../api/endpoints";
import type { AngebotPosition, AngebotPositionstyp } from "../../types";
import { validierePosition } from "../../utils/angebot";
import { SegmentedControl } from "../apple/SegmentedControl";
import { Sheet } from "../apple/Sheet";
import { FehlerMeldung } from "../Hinweiskasten";

const FORM_ID = "angebot-position-formular";

const TYP_OPTIONEN: { wert: AngebotPositionstyp; label: string }[] = [
  { wert: "material", label: "Material" },
  { wert: "arbeitszeit", label: "Arbeitszeit" },
];

/** Bearbeiten einer Angebotsposition im Entwurf. Löschen liegt bewusst im
 * Sheet hinter einem zweiten Tipp statt als Schnell-Button in der Zeile: auf dem
 * Handy trifft man den sonst leicht beim Scrollen. */
export function AngebotPositionSheet({
  angebotId,
  position,
  onClose,
}: {
  angebotId: string;
  position: AngebotPosition;
  onClose: () => void;
}) {
  // Der Aufrufer mountet das Sheet nur für eine gewählte Position (mit key),
  // so startet der Formularstand ohne Effekt-Synchronisierung daraus.
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    artikelnummer: position.artikelnummer ?? "",
    beschreibung: position.beschreibung,
    menge: position.menge,
    einheit: position.einheit,
    einzelpreis: position.einzelpreis,
    positionstyp: position.positionstyp,
  });
  const [fehler, setFehler] = useState<string | null>(null);
  const [loeschenBestaetigen, setLoeschenBestaetigen] = useState(false);

  const nachErfolg = () => {
    queryClient.invalidateQueries({ queryKey: ["angebot", angebotId] });
    queryClient.invalidateQueries({ queryKey: ["angebote"] });
    onClose();
  };
  const beiFehler = (err: unknown) =>
    setFehler(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen.");

  const speichern = useMutation({
    mutationFn: () =>
      angeboteApi.updatePosition(angebotId, position.id, {
        artikelnummer: form.artikelnummer.trim() || null,
        beschreibung: form.beschreibung.trim(),
        menge: form.menge.replace(",", "."),
        einheit: form.einheit.trim(),
        einzelpreis: form.einzelpreis.replace(",", "."),
        positionstyp: form.positionstyp,
      }),
    onSuccess: nachErfolg,
    onError: beiFehler,
  });

  const loeschen = useMutation({
    mutationFn: () => angeboteApi.removePosition(angebotId, position.id),
    onSuccess: nachErfolg,
    onError: beiFehler,
  });

  function absenden(e: FormEvent) {
    e.preventDefault();
    const problem = validierePosition(form);
    setFehler(problem);
    if (!problem) speichern.mutate();
  }

  return (
    <Sheet
      offen
      onClose={onClose}
      titel="Position bearbeiten"
      links={
        <button type="button" onClick={onClose} className="text-[17px] text-tint">
          Abbrechen
        </button>
      }
      rechts={
        <button
          type="submit"
          form={FORM_ID}
          disabled={speichern.isPending || loeschen.isPending}
          className="text-[17px] font-semibold text-tint disabled:opacity-40"
        >
          Speichern
        </button>
      }
    >
      <form id={FORM_ID} onSubmit={absenden} className="space-y-4 p-4">
        {fehler && <FehlerMeldung meldung={fehler} alsKasten />}

        <SegmentedControl
          ariaLabel="Positionstyp"
          optionen={TYP_OPTIONEN}
          wert={form.positionstyp}
          onChange={(positionstyp) => setForm({ ...form, positionstyp })}
          groesse="mobil"
          volleBreite
        />

        <div>
          <label htmlFor="angebot-pos-artikelnummer" className="mb-1 block text-xs font-medium text-label2">
            Art-Nr. <span className="font-normal text-label3">(optional)</span>
          </label>
          <input
            id="angebot-pos-artikelnummer"
            value={form.artikelnummer}
            onChange={(e) => setForm({ ...form, artikelnummer: e.target.value })}
            className="field-ap"
          />
        </div>

        <div>
          <label htmlFor="angebot-pos-beschreibung" className="mb-1 block text-xs font-medium text-label2">
            Beschreibung
          </label>
          <input
            id="angebot-pos-beschreibung"
            value={form.beschreibung}
            onChange={(e) => setForm({ ...form, beschreibung: e.target.value })}
            className="field-ap"
          />
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div>
            <label htmlFor="angebot-pos-menge" className="mb-1 block text-xs font-medium text-label2">
              Menge
            </label>
            <input
              id="angebot-pos-menge"
              type="number"
              step="0.01"
              min="0"
              inputMode="decimal"
              value={form.menge}
              onChange={(e) => setForm({ ...form, menge: e.target.value })}
              className="field-ap"
            />
          </div>
          <div>
            <label htmlFor="angebot-pos-einheit" className="mb-1 block text-xs font-medium text-label2">
              Einheit
            </label>
            <input
              id="angebot-pos-einheit"
              value={form.einheit}
              onChange={(e) => setForm({ ...form, einheit: e.target.value })}
              className="field-ap"
            />
          </div>
          <div>
            <label htmlFor="angebot-pos-preis" className="mb-1 block text-xs font-medium text-label2">
              Preis (€)
            </label>
            <input
              id="angebot-pos-preis"
              type="number"
              step="0.01"
              min="0"
              inputMode="decimal"
              value={form.einzelpreis}
              onChange={(e) => setForm({ ...form, einzelpreis: e.target.value })}
              className="field-ap"
            />
          </div>
        </div>

        <div className="border-t-[0.5px] border-sep pt-4">
          {loeschenBestaetigen ? (
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setLoeschenBestaetigen(false)}
                className="btn-touch btn-ap flex-1 text-sm"
              >
                Behalten
              </button>
              <button
                type="button"
                onClick={() => loeschen.mutate()}
                disabled={loeschen.isPending}
                className="btn-touch flex-1 rounded-md bg-st-fehlt-dot px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                Position endgültig löschen
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setLoeschenBestaetigen(true)}
              className="btn-touch w-full text-center text-[17px] text-st-fehlt"
            >
              Position löschen
            </button>
          )}
        </div>
      </form>
    </Sheet>
  );
}
