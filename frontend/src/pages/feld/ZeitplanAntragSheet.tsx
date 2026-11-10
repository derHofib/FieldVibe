import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../../api/client";
import { zeitplanApi } from "../../api/endpoints";
import { SegmentedControl } from "../../components/apple/SegmentedControl";
import { Sheet } from "../../components/apple/Sheet";
import {
  ANTRAG_ART_LABEL,
  antragFehler,
  antragVorbelegung,
  baueAntrag,
  beantragbareArten,
  endeNachVerschieben,
} from "../../office/projekte/zeitplan/antragLogik";
import { formatKurz, parseTag } from "../../office/projekte/zeitplan/zeitplanLogik";
import type { ZeitplanAntragArt, ZeitplanElement } from "../../types";

const FORM_ID = "zeitplan-antrag-form";
const GRUENDE = ["Material fehlt", "Vorarbeit nicht fertig", "Zugang nicht möglich", "Schlechtes Wetter"];

/** Feld-App: Änderung am Zeitplan beantragen. Ändert den Plan nicht selbst -- das Büro entscheidet. */
export function ZeitplanAntragSheet({
  projektId,
  element,
  onClose,
}: {
  projektId: string;
  element: ZeitplanElement;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const arten = beantragbareArten(element);
  const [art, setArt] = useState<ZeitplanAntragArt>(arten[0] ?? "problem");
  const [daten, setDaten] = useState(() => antragVorbelegung(element));
  const [begruendung, setBegruendung] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);

  const senden = useMutation({
    mutationFn: () => zeitplanApi.createAntrag(projektId, baueAntrag(element, art, daten, begruendung)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["zeitplan-antraege", projektId] });
      queryClient.invalidateQueries({ queryKey: ["projekt-zeitplan", projektId] });
      onClose();
    },
    onError: (e) =>
      setFehler(e instanceof ApiError ? e.message : "Der Antrag konnte nicht gesendet werden. Bitte später erneut versuchen."),
  });

  function absenden(e: React.FormEvent) {
    e.preventDefault();
    const f = antragFehler(element, art, daten, begruendung);
    setFehler(f);
    if (!f) senden.mutate();
  }

  const neuesEnde = art === "verschieben" ? endeNachVerschieben(element, daten.start) : null;

  return (
    <Sheet
      offen
      onClose={onClose}
      titel="Änderung beantragen"
      links={
        <button type="button" onClick={onClose} className="btn-touch text-[17px] text-tint-text">
          Abbrechen
        </button>
      }
      rechts={
        <button
          type="submit"
          form={FORM_ID}
          disabled={senden.isPending}
          className="btn-touch text-[17px] font-semibold text-tint-text disabled:opacity-50"
        >
          Senden
        </button>
      }
    >
      <form id={FORM_ID} onSubmit={absenden} className="space-y-4 p-4">
        <p className="truncate text-[15px] font-semibold text-label">{element.titel}</p>

        {arten.length > 1 && (
          <SegmentedControl
            ariaLabel="Art der Änderung"
            optionen={arten.map((a) => ({ wert: a, label: ANTRAG_ART_LABEL[a] }))}
            wert={art}
            onChange={setArt}
            groesse="mobil"
            volleBreite
          />
        )}
        {element.datum_gesperrt && (
          <p className="text-[13px] text-label2">Das Datum kommt aus dem Liefertermin der Bestellung — hier lässt sich nur ein Problem melden.</p>
        )}

        {art === "verschieben" && (
          <div className="space-y-1">
            <label htmlFor="antrag-start" className="text-[13px] font-medium text-label2">
              Neuer Start
            </label>
            <input
              id="antrag-start"
              type="date"
              required
              value={daten.start}
              onChange={(e) => setDaten({ ...daten, start: e.target.value })}
              className="field-ap"
            />
            {neuesEnde && element.typ !== "meilenstein" && (
              <p className="text-[13px] text-label2">
                Bisherige Dauer bleibt: bis {formatKurz(parseTag(neuesEnde))}
              </p>
            )}
          </div>
        )}
        {art === "dauer_aendern" && (
          <div className="space-y-1">
            <label htmlFor="antrag-ende" className="text-[13px] font-medium text-label2">
              Neues Ende
            </label>
            <input
              id="antrag-ende"
              type="date"
              required
              min={element.start_am ?? undefined}
              value={daten.ende}
              onChange={(e) => setDaten({ ...daten, ende: e.target.value })}
              className="field-ap"
            />
          </div>
        )}

        <div className="space-y-1.5">
          <label htmlFor="antrag-begruendung" className="text-[13px] font-medium text-label2">
            Begründung (Pflicht)
          </label>
          <textarea
            id="antrag-begruendung"
            value={begruendung}
            onChange={(e) => setBegruendung(e.target.value)}
            rows={3}
            maxLength={2000}
            placeholder="Was läuft auf der Baustelle nicht richtig?"
            className="field-ap"
          />
          <div className="flex flex-wrap gap-1.5">
            {GRUENDE.map((g) => (
              <button
                key={g}
                type="button"
                onClick={() => setBegruendung((b) => (b.trim() ? `${b.trim()}. ${g}` : g))}
                className="rounded-full bg-fill px-3 py-1 text-[13px] text-label"
              >
                {g}
              </button>
            ))}
          </div>
        </div>

        {fehler && (
          <p role="alert" className="text-sm text-st-fehlt">
            {fehler}
          </p>
        )}
      </form>
    </Sheet>
  );
}
