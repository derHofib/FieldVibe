import { ArrowRight, ChevronDown, CircleCheck, Play, RotateCcw } from "lucide-react";

import { AktionsMenue, type AktionsMenueEintrag } from "../../../components/AktionsMenue";
import type { IconTone } from "../../../components/IconBadge";
import { StatusBadge } from "../../../components/StatusBadge";
import type { VorgangStatus } from "../../../types";

export const VORGANG_STATUS_LABEL: Record<VorgangStatus, string> = {
  neu: "Neu",
  geplant: "Geplant",
  in_arbeit: "In Arbeit",
  wartet_kunde: "Wartet auf Kunde",
  abgeschlossen: "Abgeschlossen",
  abgerechnet: "Abgerechnet",
  storniert: "Storniert",
};

const STATUS_TONE: Record<VorgangStatus, IconTone> = {
  neu: "sky",
  geplant: "violet",
  in_arbeit: "amber",
  wartet_kunde: "amber",
  abgeschlossen: "emerald",
  abgerechnet: "slate",
  storniert: "slate",
};

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
 * für "Wartet auf Kunde" bleibt beim Aufrufer in `onWaehle`. */
export function VorgangStatusAktionen({
  status,
  darfAendern,
  pending,
  onWaehle,
}: {
  status: VorgangStatus;
  darfAendern: boolean;
  pending: boolean;
  onWaehle: (status: VorgangStatus) => void;
}) {
  const schritt = NAECHSTER_SCHRITT[status];
  const wiederOeffnen = status === "abgeschlossen" || status === "storniert" || status === "abgerechnet";
  const eintraege: (AktionsMenueEintrag | "trenner")[] = SETZBAR.filter(
    (s) => s !== status && s !== schritt?.nach && s !== "storniert",
  ).map((s) => ({
    label: wiederOeffnen ? `Wieder öffnen als „${VORGANG_STATUS_LABEL[s]}“` : `Status: ${VORGANG_STATUS_LABEL[s]}`,
    icon: ArrowRight,
    onClick: () => onWaehle(s),
  }));
  if (status !== "storniert") {
    eintraege.push("trenner", {
      label: "Vorgang stornieren",
      destruktiv: true,
      onClick: () => onWaehle("storniert"),
    });
  }

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <StatusBadge label={VORGANG_STATUS_LABEL[status]} tone={STATUS_TONE[status]} />
      {darfAendern && schritt && (
        <button
          onClick={() => onWaehle(schritt.nach)}
          disabled={pending}
          className="btn-touch btn-clay flex items-center gap-1.5 rounded-full bg-linear-to-r from-cyan-500 to-blue-600 px-4 text-sm font-semibold text-white disabled:opacity-50"
        >
          <schritt.icon size={15} strokeWidth={2.25} /> {schritt.label}
        </button>
      )}
      {darfAendern && eintraege.length > 0 && (
        <AktionsMenue
          label="Status ändern"
          eintraege={eintraege}
          ausloeser={() => (
            <span className="btn-touch flex items-center gap-1 rounded-full bg-slate-100 px-3 text-sm font-medium text-slate-600 dark:bg-stone-800 dark:text-stone-300">
              Status ändern <ChevronDown size={14} strokeWidth={2} />
            </span>
          )}
        />
      )}
    </div>
  );
}
