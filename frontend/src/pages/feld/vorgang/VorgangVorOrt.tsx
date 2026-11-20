import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MapPin, Phone } from "lucide-react";
import { useState } from "react";

import { vorgaengeApi } from "../../../api/endpoints";
import { ABSCHNITT_AKTION, Abschnitt } from "./Abschnitt";
import type { Adresse, Kunde, Vorgang } from "../../../types";
import { telHref } from "../../../utils/vorOrt";
import { VorOrtKontakteAbschnitt } from "../vorOrt/VorOrtKontakteAbschnitt";
import { adresseAlsZeile } from "./konstanten";

const ZEILE_ICON = "flex h-7 w-7 shrink-0 items-center justify-center rounded-[var(--radius-ap-md)] bg-fill text-label2";

/** Gruppen "Vor Ort" (Adresse, Einheit, Kontakte vor Ort inkl. geerbter) und "Auftraggeber" in der Vorgang-Übersicht.
 * Alle Daten stammen aus der Vorgang-Detail-Antwort, es gibt keine eigene Abfrage. */
export function VorgangVorOrt({
  vorgang,
  kunde,
  anzeigeAdresse,
  darfBearbeiten,
  layout,
}: {
  vorgang: Vorgang;
  kunde: Kunde | undefined;
  anzeigeAdresse: Adresse | null;
  darfBearbeiten: boolean;
  layout: "feld" | "office";
}) {
  const adresse = adresseAlsZeile(anzeigeAdresse);
  const einheit = vorgang.einheit?.trim() || null;
  const sachbearbeitung = vorgang.auftraggeber_ansprechpartner ?? null;
  const zeichen = vorgang.auftrag_kunden_referenz?.trim() || null;
  const feld = layout === "feld";
  const queryClient = useQueryClient();
  const [einheitBearbeiten, setEinheitBearbeiten] = useState(false);
  const [einheitText, setEinheitText] = useState("");
  const einheitSpeichern = useMutation({
    meta: { erfolg: "Gespeichert" },
    mutationFn: () => vorgaengeApi.update(vorgang.id, { einheit: einheitText.trim() || null }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["vorgang", vorgang.id] });
      void queryClient.invalidateQueries({ queryKey: ["feed"] });
      setEinheitBearbeiten(false);
    },
  });

  return (
    <>
      <Abschnitt
        titel="Vor Ort"
        aktion={
          darfBearbeiten && !einheitBearbeiten ? (
            <button
              type="button"
              onClick={() => {
                setEinheitText(vorgang.einheit ?? "");
                setEinheitBearbeiten(true);
              }}
              className={ABSCHNITT_AKTION}
            >
              Einheit ändern
            </button>
          ) : undefined
        }
      >
        {einheitBearbeiten && (
          <div className="mb-2 flex gap-2">
            <input
              aria-label="Einheit"
              autoFocus
              value={einheitText}
              onChange={(e) => setEinheitText(e.target.value)}
              placeholder="z. B. Whg. 3, 2. OG links"
              className="field-ap flex-1"
            />
            <button type="button" onClick={() => setEinheitBearbeiten(false)} className="btn-touch btn-ap px-3 text-sekundaer">
              Abbrechen
            </button>
            <button
              type="button"
              disabled={einheitSpeichern.isPending}
              onClick={() => einheitSpeichern.mutate()}
              className="btn-touch btn-ap-primary px-3 text-sekundaer"
            >
              Speichern
            </button>
          </div>
        )}
        {(adresse || einheit) && (
          <div className="mb-1 flex items-start gap-3 pb-2">
            <span className={ZEILE_ICON}>
              <MapPin size={15} strokeWidth={1.5} aria-hidden="true" />
            </span>
            <div className="min-w-0">
              {adresse && <p className={`${feld ? "text-zeile" : "text-fliess"} text-label`}>{adresse}</p>}
              {einheit && <p className="text-sekundaer text-label2">{einheit}</p>}
            </div>
          </div>
        )}
        <VorOrtKontakteAbschnitt
          eingebettet
          ziel="vorgang"
          zielId={vorgang.id}
          kundeId={vorgang.kunde_id}
          standortId={vorgang.standort_id}
          darfBearbeiten={darfBearbeiten}
          layout={layout}
          kontakte={vorgang.vor_ort_kontakte ?? []}
        />
      </Abschnitt>

      {kunde && (
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
      )}
    </>
  );
}
