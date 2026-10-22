import { FileText } from "lucide-react";
import { bestaetigen } from "../../../components/apple/BestaetigungsDialog";
import { useAuth } from "../../../context/AuthContext";
import type { MangelSchweregrad } from "../../../types";
import {
  MANGEL_STATUS_LABEL, SCHWEREGRAD_BADGE, SCHWEREGRAD_LABEL, SCHWEREGRAD_OPTIONEN,
} from "./konstanten";
import type { MaengelDaten } from "./useVorgangMaengel";

interface MaengelAbschnittProps {
  istAktiverTab: (ziel: string) => boolean;
  layout: "kompakt" | "dicht";
  tabPanelProps: (ziel: string) => { role?: "tabpanel"; "aria-labelledby"?: string };
  maengelDaten: MaengelDaten;
}

/** Mängel melden, bearbeiten und daraus Angebot bzw. Protokoll erzeugen. */
export function MaengelAbschnitt({
  istAktiverTab, layout, tabPanelProps, maengelDaten,
}: MaengelAbschnittProps) {
  const {
    angebotAusMaengelnMutation, deleteMangelMutation, maengel, maengelProtokollMutation,
    mangelBeschreibung, mangelErfassen, mangelMutation, mangelSchweregrad, mangelStatusMutation,
    setMangelBeschreibung, setMangelSchweregrad, setShowMangelForm, showMangelForm,
  } = maengelDaten;
  const { currentUser, hatRecht } = useAuth();
  const kannDisponieren = hatRecht("vorgaenge", "bearbeiten");
  const kannPapierkorbLoeschen = currentUser?.role === "loesch_operativ";
  return (
    <div
      id="abschnitt-maengel"
      className={`scroll-mt-4 card-ap p-3 ${istAktiverTab("abschnitt-maengel") ? "" : "hidden"}`}
      {...tabPanelProps("abschnitt-maengel")}
    >
      <div className="mb-2 flex items-center justify-between">
        {/* Leerer Abschnitt auf Mobile: Ueberschrift entfaellt, die
         * Leer-Meldung nennt den Abschnitt stattdessen selbst (gleiches
         * Muster wie in TermineAbschnitt). */}
        {!(layout !== "dicht" && (maengel ?? []).length === 0 && !showMangelForm) && (
          <h2 className="font-heading text-sm font-semibold uppercase tracking-wide text-label">Mängel</h2>
        )}
        <div className="flex items-center gap-3">
          {(maengel ?? []).length > 0 && (
            <button
              onClick={() => maengelProtokollMutation.mutate()}
              disabled={maengelProtokollMutation.isPending}
              className="btn-touch flex items-center gap-1 text-xs font-medium text-label2"
            >
              <FileText size={13} strokeWidth={2} /> Protokoll
            </button>
          )}
          <button
            onClick={() => setShowMangelForm((v) => !v)}
            className="btn-touch text-xs font-medium text-tint"
          >
            {showMangelForm ? "Abbrechen" : "+ Mangel melden"}
          </button>
        </div>
      </div>

      {showMangelForm && (
        <div className="mb-2 space-y-2 border border-sepstrong p-2">
          <textarea
            value={mangelBeschreibung}
            onChange={(e) => setMangelBeschreibung(e.target.value)}
            placeholder="Was ist defekt?"
            rows={2}
            className="w-full resize-none border border-sep bg-transparent p-2 text-sm text-label"
          />
          <select
            value={mangelSchweregrad}
            onChange={(e) => setMangelSchweregrad(e.target.value as MangelSchweregrad)}
            className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
          >
            {SCHWEREGRAD_OPTIONEN.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          <button
            disabled={!mangelBeschreibung.trim() || mangelMutation.isPending}
            onClick={mangelErfassen}
            className="btn-touch btn-ap-primary w-full px-3 py-1.5 text-sm"
          >
            Erfassen
          </button>
        </div>
      )}

      {(maengel ?? []).length === 0 ? (
        <p className="text-sm text-label2">
          {layout === "dicht" || showMangelForm ? "Keine Mängel erfasst." : "Mängel: Keine erfasst."}
        </p>
      ) : (
        <div className="space-y-1.5">
          {maengel!.map((m) => (
            <div key={m.id} className="border border-sepstrong p-2 text-sm">
              <div className="flex items-start justify-between gap-2">
                <p className="text-label">{m.beschreibung}</p>
                <span className={`shrink-0 border px-2 py-0.5 text-xs font-medium ${SCHWEREGRAD_BADGE[m.schweregrad]}`}>
                  {SCHWEREGRAD_LABEL[m.schweregrad]}
                </span>
              </div>
              <div className="mt-1 flex items-center justify-between">
                <span className="text-xs text-label2">{MANGEL_STATUS_LABEL[m.status]}</span>
                <div className="flex gap-2">
                  {m.status === "offen" && (
                    <>
                      <button
                        onClick={() => mangelStatusMutation.mutate({ mangelId: m.id, status: "behoben" })}
                        className="btn-touch text-xs font-medium text-st-erledigt"
                      >
                        Behoben
                      </button>
                      <button
                        onClick={() => mangelStatusMutation.mutate({ mangelId: m.id, status: "abgelehnt" })}
                        className="btn-touch text-xs font-medium text-st-fehlt"
                      >
                        Verwerfen
                      </button>
                    </>
                  )}
                  {kannPapierkorbLoeschen && (
                    <button
                      onClick={async () => {
                        if (await bestaetigen("Mangel wirklich löschen?")) {
                          deleteMangelMutation.mutate(m.id);
                        }
                      }}
                      disabled={deleteMangelMutation.isPending}
                      className="btn-touch text-xs font-medium text-st-fehlt"
                    >
                      Löschen
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {kannDisponieren && (maengel ?? []).some((m) => m.status === "offen") && (
        <button
          onClick={() =>
            angebotAusMaengelnMutation.mutate(maengel!.filter((m) => m.status === "offen").map((m) => m.id))
          }
          disabled={angebotAusMaengelnMutation.isPending}
          className="btn-touch mt-2 btn-ap w-full px-3 py-1.5 text-sm"
        >
          Angebot aus offenen Mängeln erstellen
        </button>
      )}
    </div>
  );
}
