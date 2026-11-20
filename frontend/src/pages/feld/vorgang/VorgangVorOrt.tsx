import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Phone } from "lucide-react";
import { useState } from "react";

import { vorgaengeApi } from "../../../api/endpoints";
import { Abschnitt } from "./Abschnitt";
import type { Kunde, Vorgang } from "../../../types";
import { telHref } from "../../../utils/vorOrt";
import { VorOrtKontakteAbschnitt } from "../vorOrt/VorOrtKontakteAbschnitt";

/** Einheit unter der Adresse im Einsatzort (z. B. "Whg. 3, 2. OG links"), direkt änderbar. */
export function EinheitZeile({ vorgang, darfBearbeiten }: { vorgang: Vorgang; darfBearbeiten: boolean }) {
  const queryClient = useQueryClient();
  const [bearbeiten, setBearbeiten] = useState(false);
  const [text, setText] = useState("");
  const einheit = vorgang.einheit?.trim() || null;
  const speichern = useMutation({
    meta: { erfolg: "Gespeichert" },
    mutationFn: () => vorgaengeApi.update(vorgang.id, { einheit: text.trim() || null }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["vorgang", vorgang.id] });
      void queryClient.invalidateQueries({ queryKey: ["feed"] });
      setBearbeiten(false);
    },
  });

  if (bearbeiten) {
    return (
      <div className="mt-1 flex gap-2">
        <input
          aria-label="Einheit"
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="z. B. Whg. 3, 2. OG links"
          className="field-ap flex-1"
        />
        <button type="button" onClick={() => setBearbeiten(false)} className="btn-touch btn-ap px-3 text-sekundaer">
          Abbrechen
        </button>
        <button type="button" disabled={speichern.isPending} onClick={() => speichern.mutate()} className="btn-touch btn-ap-primary px-3 text-sekundaer">
          Speichern
        </button>
      </div>
    );
  }
  if (!einheit && !darfBearbeiten) return null;
  return (
    <p className="text-sekundaer text-label2">
      {einheit}
      {darfBearbeiten && (
        <>
          {einheit && " · "}
          <button
            type="button"
            onClick={() => {
              setText(vorgang.einheit ?? "");
              setBearbeiten(true);
            }}
            className="font-medium text-tint-text hover:underline"
          >
            {einheit ? "Einheit ändern" : "Einheit hinzufügen"}
          </button>
        </>
      )}
    </p>
  );
}

/** Gruppe "Vor Ort": nur die Kontakte (inkl. geerbter); Adresse und Einheit stehen im Einsatzort davor. */
export function VorgangKontakteGruppe({
  vorgang,
  darfBearbeiten,
  darfKorrigieren,
  layout,
}: {
  vorgang: Vorgang;
  darfBearbeiten: boolean;
  darfKorrigieren: boolean;
  layout: "feld" | "office";
}) {
  return (
    <Abschnitt titel="Vor Ort">
      <VorOrtKontakteAbschnitt
        eingebettet
        ziel="vorgang"
        zielId={vorgang.id}
        kundeId={vorgang.kunde_id}
        standortId={vorgang.standort_id}
        darfBearbeiten={darfBearbeiten}
        darfKorrigieren={darfKorrigieren}
        layout={layout}
        kontakte={vorgang.vor_ort_kontakte ?? []}
      />
    </Abschnitt>
  );
}

/** Gruppe "Auftraggeber" in der Vorgang-Übersicht. Alle Daten stammen aus der Vorgang-Detail-Antwort. */
export function VorgangAuftraggeber({ vorgang, kunde }: { vorgang: Vorgang; kunde: Kunde | undefined }) {
  const sachbearbeitung = vorgang.auftraggeber_ansprechpartner ?? null;
  const zeichen = vorgang.auftrag_kunden_referenz?.trim() || null;
  if (!kunde) return null;
  return (
    <Abschnitt titel="Auftraggeber">
      <dl className="space-y-1.5 text-fliess">
        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-label2">Kunde</dt>
          <dd className="text-right font-medium text-label">{kunde.name}</dd>
        </div>
        {sachbearbeitung && (
          <div className="flex items-center justify-between gap-3">
            <dt className="text-label2">Sachbearbeitung</dt>
            <dd className="flex items-center gap-2 text-right font-medium text-label">
              {sachbearbeitung.name}
              {sachbearbeitung.telefon && (
                <a
                  href={telHref(sachbearbeitung.telefon)}
                  aria-label={`${sachbearbeitung.name} anrufen`}
                  className="inline-flex items-center gap-1 text-sekundaer font-medium text-tint-text hover:underline"
                >
                  <Phone size={14} strokeWidth={2} aria-hidden="true" />
                  {sachbearbeitung.telefon}
                </a>
              )}
            </dd>
          </div>
        )}
        {zeichen && (
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-label2">Zeichen</dt>
            <dd className="text-right font-medium text-label">{zeichen}</dd>
          </div>
        )}
      </dl>
    </Abschnitt>
  );
}
