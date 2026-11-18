import { ArrowRight, ChevronDown, CircleCheck, Play, RotateCcw } from "lucide-react";
import type { ReactNode } from "react";

import { useBestaetigung } from "../../../components/ConfirmDialog";
import { PulldownMenu, type PulldownItem } from "../../../components/apple/PulldownMenu";
import { STATUS_LABEL } from "../../../config/vorgangDarstellung";
import type { VorgangStatus } from "../../../types";

// "abgerechnet" fehlt bewusst: das Backend lässt es nicht per PATCH zu
// (VorgangStatusSetzbar), es entsteht nur über die bezahlte Rechnung.
const SETZBAR: VorgangStatus[] = ["neu", "geplant", "in_arbeit", "wartet_kunde", "abgeschlossen", "storniert"];

// Der nächste sinnvolle Schritt je Status; alles Übrige steht im Menü.
const NAECHSTER_SCHRITT: Partial<Record<VorgangStatus, { nach: VorgangStatus; label: string; icon: typeof Play }>> = {
  neu: { nach: "in_arbeit", label: "Starten", icon: Play },
  geplant: { nach: "in_arbeit", label: "Starten", icon: Play },
  in_arbeit: { nach: "abgeschlossen", label: "Fertig melden", icon: CircleCheck },
  wartet_kunde: { nach: "in_arbeit", label: "Wieder aufnehmen", icon: RotateCcw },
};

/** Statuswechsel als Aktionsbutton für den nächsten Schritt plus Menü für
 * alle übrigen Wechsel (ersetzt das rohe Status-Select). Das Dialog-Handling
 * für "Wartet auf Kunde" bleibt beim Aufrufer in `onWaehle`. Die Status-Pille
 * steht an der Nummer im Kopf, nicht mehr hier (sonst doppelt). */
export function VorgangStatusAktionen({
  status,
  darfAendern,
  pending,
  onWaehle,
  primaer = true,
  ersatzSchritt,
  children,
}: {
  status: VorgangStatus;
  darfAendern: boolean;
  pending: boolean;
  onWaehle: (status: VorgangStatus) => void;
  /** Auf false, wenn die Seite schon eine gefüllte Primäraktion zeigt (klebende Leiste): pro Ansicht nur eine. */
  primaer?: boolean;
  /** Hauptaktion für Status ohne eigenen nächsten Schritt (abgeschlossen: "Rechnung erstellen"). */
  ersatzSchritt?: { label: string; onClick: () => void; disabled?: boolean };
  /** Zusatzaktionen hinter dem Status-Menü. */
  children?: ReactNode;
}) {
  const bestaetigen = useBestaetigung();
  const schritt = NAECHSTER_SCHRITT[status];
  const wiederOeffnen = status === "abgeschlossen" || status === "storniert" || status === "abgerechnet";
  const items: PulldownItem[] = SETZBAR.filter((s) => s !== status && s !== schritt?.nach && s !== "storniert").map(
    (s) => ({
      label: wiederOeffnen ? `Wieder öffnen als „${STATUS_LABEL[s]}“` : `Status: ${STATUS_LABEL[s]}`,
      icon: ArrowRight,
      onSelect: () => onWaehle(s),
    }),
  );
  if (status !== "storniert") {
    items.push("trenner", { label: "Vorgang stornieren", destruktiv: true, onSelect: async () => {
        // Storno ist im Alltag nicht rückgängig gemeint (verschwindet aus dem Feed), daher nicht ohne Rückfrage.
        if (!(await bestaetigen({ titel: "Vorgang stornieren?", text: "Der Vorgang verschwindet aus den offenen Vorgängen. Du kannst ihn später über „Status ändern“ wieder öffnen.", bestaetigenLabel: "Stornieren", destruktiv: true }))) return;
        onWaehle("storniert");
      },
    });
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {darfAendern && schritt && (
        <button onClick={() => onWaehle(schritt.nach)} disabled={pending} className={`min-h-11 md:min-h-8 text-sekundaer whitespace-nowrap px-4 ${primaer ? "btn-ap-primary" : "btn-ap"}`}>
          <schritt.icon size={15} strokeWidth={2} aria-hidden="true" /> {schritt.label}
        </button>
      )}
      {darfAendern && !schritt && ersatzSchritt && (
        <button onClick={ersatzSchritt.onClick} disabled={ersatzSchritt.disabled} className={`min-h-11 md:min-h-8 text-sekundaer whitespace-nowrap px-4 ${primaer ? "btn-ap-primary" : "btn-ap"}`}>
          {ersatzSchritt.label}
        </button>
      )}
      {darfAendern && items.length > 0 && (
        <PulldownMenu
          ariaLabel="Status ändern"
          items={items}
          trigger={({ offen, toggeln, triggerRef }) => (
            <button
              ref={triggerRef}
              type="button"
              onClick={toggeln}
              aria-haspopup="menu"
              aria-expanded={offen}
              className="min-h-11 md:min-h-8 btn-ap text-sekundaer whitespace-nowrap px-3"
            >
              Status ändern <ChevronDown size={14} strokeWidth={2} aria-hidden="true" />
            </button>
          )}
        />
      )}
      {children}
    </div>
  );
}
