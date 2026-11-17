import { ArrowUpDown } from "lucide-react";

import { SORTIERUNGEN } from "../config/vorgaengeFilter";
import { PulldownMenu } from "./apple/PulldownMenu";

/** Sortierung ist kein Filter und bleibt neben dem Ansicht-Umschalter ein eigenes Bedienelement. */
export function VorgaengeSortierMenue({ wert, onWechsel }: { wert: string; onWechsel: (s: string) => void }) {
  return (
    <PulldownMenu
      ariaLabel="Sortieren"
      items={SORTIERUNGEN.map((s) => ({ label: s.label, aktiv: s.wert === wert, onSelect: () => onWechsel(s.wert) }))}
      trigger={({ toggeln, triggerRef, offen }) => (
        <button
          ref={triggerRef}
          type="button"
          onClick={toggeln}
          aria-haspopup="menu"
          aria-expanded={offen}
          className="btn-ap-toolbar"
          title="Sortieren"
          aria-label="Sortieren"
        >
          <ArrowUpDown size={14} strokeWidth={2} aria-hidden="true" />
        </button>
      )}
    />
  );
}
