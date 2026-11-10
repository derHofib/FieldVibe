import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, MessageSquareWarning } from "lucide-react";
import { useState } from "react";

import { ApiError } from "../../../api/client";
import { zeitplanApi } from "../../../api/endpoints";
import { Sheet } from "../../../components/apple/Sheet";
import { StatusPille } from "../../../components/apple/StatusPille";
import { EmptyState } from "../../../components/EmptyState";
import type { Zeitplan, ZeitplanAntrag } from "../../../types";
import {
  ANTRAG_ART_LABEL,
  ANTRAG_STATUS_LABEL,
  ANTRAG_STATUS_TOKEN,
  antragZeitText,
  offeneAntraege,
} from "./antragLogik";

function datumZeit(iso: string): string {
  return new Date(iso).toLocaleString("de-DE", { timeZone: "Europe/Berlin", dateStyle: "short", timeStyle: "short" });
}

function AntragKarte({
  antrag,
  projektId,
  onEntschieden,
}: {
  antrag: ZeitplanAntrag;
  projektId: string;
  onEntschieden: (zp: Zeitplan) => void;
}) {
  const queryClient = useQueryClient();
  const [modus, setModus] = useState<"annehmen" | "ablehnen" | null>(null);
  const [text, setText] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const offen = antrag.status === "offen";

  const entscheiden = useMutation({
    mutationFn: () =>
      modus === "annehmen"
        ? zeitplanApi.antragAnnehmen(projektId, antrag.id, text.trim())
        : zeitplanApi.antragAblehnen(projektId, antrag.id, text.trim()),
    onSuccess: (antwort) => {
      queryClient.invalidateQueries({ queryKey: ["zeitplan-antraege", projektId] });
      onEntschieden(antwort.zeitplan);
      setModus(null);
      setText("");
    },
    onError: (e) => {
      setFehler(e instanceof ApiError ? e.message : "Der Antrag konnte nicht bearbeitet werden.");
      // Konflikt (z. B. Schritt gelöscht, bereits bearbeitet): Liste neu laden.
      queryClient.invalidateQueries({ queryKey: ["zeitplan-antraege", projektId] });
    },
  });

  const ablehnenOhneText = modus === "ablehnen" && !text.trim();

  return (
    <li className="card-ap space-y-2 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-[15px] font-semibold text-label">{antrag.element_titel}</p>
          <p className="text-[13px] text-label2">
            {ANTRAG_ART_LABEL[antrag.art]} · {antragZeitText(antrag)}
          </p>
        </div>
        <StatusPille status={ANTRAG_STATUS_TOKEN[antrag.status]} label={ANTRAG_STATUS_LABEL[antrag.status]} />
      </div>
      <p className="rounded-[8px] bg-fill px-2.5 py-1.5 text-[14px] whitespace-pre-wrap text-label">{antrag.begruendung}</p>
      <p className="text-xs text-label2">
        {antrag.erstellt_von_name ?? "Unbekannt"} · {datumZeit(antrag.erstellt_am)}
      </p>
      {antrag.antwort && (
        <p className="text-[13px] text-label2">
          <span className="font-medium text-label">Antwort{antrag.bearbeitet_von_name ? ` von ${antrag.bearbeitet_von_name}` : ""}:</span>{" "}
          {antrag.antwort}
        </p>
      )}

      {offen && modus === null && (
        <div className="flex gap-2 pt-1">
          <button type="button" onClick={() => setModus("annehmen")} className="btn-ap btn-ap-primary px-3 py-1.5 text-sm">
            Annehmen
          </button>
          <button type="button" onClick={() => setModus("ablehnen")} className="btn-ap px-3 py-1.5 text-sm text-st-fehlt">
            Ablehnen
          </button>
        </div>
      )}

      {offen && modus !== null && (
        <div className="space-y-2 pt-1">
          <label className="block text-[13px] font-medium text-label2" htmlFor={`antwort-${antrag.id}`}>
            {modus === "annehmen" ? "Kommentar (optional)" : "Begründung der Ablehnung (Pflicht)"}
          </label>
          <textarea
            id={`antwort-${antrag.id}`}
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={2}
            maxLength={2000}
            className="field-ap"
          />
          {fehler && (
            <p role="alert" className="text-sm text-st-fehlt">
              {fehler}
            </p>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              disabled={entscheiden.isPending || ablehnenOhneText}
              onClick={() => {
                setFehler(null);
                entscheiden.mutate();
              }}
              className={`btn-ap px-3 py-1.5 text-sm ${modus === "annehmen" ? "btn-ap-primary" : "text-st-fehlt"}`}
            >
              {modus === "annehmen" ? "Änderung übernehmen" : "Ablehnen"}
            </button>
            <button
              type="button"
              onClick={() => {
                setModus(null);
                setText("");
                setFehler(null);
              }}
              className="btn-ap px-3 py-1.5 text-sm"
            >
              Abbrechen
            </button>
          </div>
        </div>
      )}
      {offen && modus === null && fehler && (
        <p role="alert" className="text-sm text-st-fehlt">
          {fehler}
        </p>
      )}
    </li>
  );
}

/** Office: Änderungsanträge der Techniker zu diesem Zeitplan. Annehmen wendet
 * die Änderung serverseitig über die normale Element-Änderung an (inkl.
 * Nachfolger-Propagation) und liefert den neuen Zeitplan zurück. */
export function AntraegeSheet({
  projektId,
  onClose,
  onZeitplan,
}: {
  projektId: string;
  onClose: () => void;
  onZeitplan: (zp: Zeitplan) => void;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["zeitplan-antraege", projektId],
    queryFn: () => zeitplanApi.antraege(projektId),
  });
  const [erledigtOffen, setErledigtOffen] = useState(false);
  const offene = offeneAntraege(data ?? []);
  const erledigte = (data ?? []).filter((a) => a.status !== "offen");

  return (
    <Sheet
      offen
      onClose={onClose}
      titel="Änderungsanträge"
      rechts={
        <button type="button" onClick={onClose} className="text-[17px] font-semibold text-tint-text">
          Fertig
        </button>
      }
    >
      <div className="space-y-4 p-4">
        {isLoading ? (
          <p className="text-sm text-label2">Anträge werden geladen …</p>
        ) : error ? (
          <p role="alert" className="text-sm text-st-fehlt">
            Anträge konnten nicht geladen werden.
          </p>
        ) : (
          <>
            {offene.length === 0 ? (
              <EmptyState icon={MessageSquareWarning} text="Keine offenen Änderungsanträge." />
            ) : (
              <ul className="space-y-3" aria-label="Offene Anträge">
                {offene.map((a) => (
                  <AntragKarte key={a.id} antrag={a} projektId={projektId} onEntschieden={onZeitplan} />
                ))}
              </ul>
            )}
            {erledigte.length > 0 && (
              <section>
                <button
                  type="button"
                  onClick={() => setErledigtOffen((v) => !v)}
                  aria-expanded={erledigtOffen}
                  className="flex items-center gap-1 text-[13px] font-semibold text-label2"
                >
                  {erledigtOffen ? <ChevronDown size={15} strokeWidth={2} aria-hidden="true" /> : <ChevronRight size={15} strokeWidth={2} aria-hidden="true" />}
                  Erledigte Anträge ({erledigte.length})
                </button>
                {erledigtOffen && (
                  <ul className="mt-2 space-y-3" aria-label="Erledigte Anträge">
                    {erledigte.map((a) => (
                      <AntragKarte key={a.id} antrag={a} projektId={projektId} onEntschieden={onZeitplan} />
                    ))}
                  </ul>
                )}
              </section>
            )}
          </>
        )}
      </div>
    </Sheet>
  );
}
