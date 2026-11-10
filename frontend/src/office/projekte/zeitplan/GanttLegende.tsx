import { ChevronDown, ChevronRight, Package } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";

import { ART_ERKLAERUNG, ART_LABEL } from "./zeitplanLogik";

function Eintrag({ symbol, label }: { symbol: ReactNode; label: string }) {
  return (
    <li className="flex items-center gap-1.5">
      <span className="flex h-4 w-8 shrink-0 items-center justify-center" aria-hidden="true">
        {symbol}
      </span>
      <span>{label}</span>
    </li>
  );
}

function ArtSymbol({ art }: { art: "ende_anfang" | "anfang_anfang" | "ende_ende" }) {
  const pfad = art === "ende_anfang" ? "M2 4 H8 V12 H26" : art === "anfang_anfang" ? "M8 4 H3 V12 H26" : "M2 4 H26 V12 H8";
  const pfeil = art === "ende_ende" ? "8,12 13,9.5 13,14.5" : "26,12 21,9.5 21,14.5";
  return (
    <svg width={30} height={16} viewBox="0 0 30 16" className="text-label2">
      <path d={pfad} fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" />
      <polygon points={pfeil} fill="currentColor" />
    </svg>
  );
}

/** Kleine, einklappbare Legende unter der Zeitleiste. Eingeklappt Standard,
 * damit sie dem Plan keine Hoehe wegnimmt. */
export function GanttLegende() {
  const [offen, setOffen] = useState(false);
  return (
    <div className="rounded-[10px] bg-fill px-3 py-2 text-xs text-label2">
      <button
        type="button"
        onClick={() => setOffen((o) => !o)}
        aria-expanded={offen}
        aria-controls="zeitplan-legende"
        className="flex items-center gap-1 font-semibold text-label"
      >
        {offen ? <ChevronDown size={14} strokeWidth={2} aria-hidden="true" /> : <ChevronRight size={14} strokeWidth={2} aria-hidden="true" />}
        Legende
      </button>
      {offen && (
        <ul id="zeitplan-legende" className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2 lg:grid-cols-3">
          <Eintrag symbol={<span className="h-3 w-7 rounded-[4px] bg-tint-solid" />} label="Schritt (Balken, dunkler Anteil = Fortschritt)" />
          <Eintrag
            symbol={
              <span className="relative h-3 w-7 overflow-hidden rounded-[4px] bg-tone-violet">
                <span className="absolute inset-0 bg-black/15" />
                <span
                  className="absolute inset-0"
                  style={{ backgroundImage: "repeating-linear-gradient(45deg, rgba(255,255,255,.22) 0 2px, transparent 2px 6px)" }}
                />
              </span>
            }
            label="Fremdgewerk / Nachunternehmer"
          />
          <Eintrag symbol={<span className="h-2.5 w-2.5 rotate-45 bg-tone-amber" />} label="Meilenstein" />
          <Eintrag
            symbol={
              <span className="flex h-4 w-4 items-center justify-center rounded-[4px] bg-tone-amber">
                <Package size={11} strokeWidth={2.2} color="#1c1c1e" />
              </span>
            }
            label="Lieferung (Datum aus Bestellung, nicht verschiebbar)"
          />
          <Eintrag symbol={<span className="h-2.5 w-2.5 rounded-full border-[1.5px] border-label bg-card" />} label="Dispo-Termin des Vorgangs" />
          <Eintrag symbol={<span className="h-2.5 w-2.5 rounded-full border-[1.5px] border-card bg-st-fehlt-dot" />} label="Termin außerhalb des Plans" />
          <Eintrag
            symbol={<span className="h-3 w-3 rounded-full border-[1.5px] border-white bg-st-arbeit-dot shadow-[0_0_0_0.5px_var(--sepstrong)]" />}
            label="Verknüpfter Vorgang (Farbe = Status)"
          />
          {(["ende_anfang", "anfang_anfang", "ende_ende"] as const).map((art) => (
            <Eintrag key={art} symbol={<ArtSymbol art={art} />} label={`${ART_LABEL[art]}: ${ART_ERKLAERUNG[art]}`} />
          ))}
        </ul>
      )}
    </div>
  );
}
