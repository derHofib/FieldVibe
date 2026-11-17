import { Check, ChevronRight, type LucideIcon } from "lucide-react";
import { useCallback, useId, useState, type KeyboardEvent, type ReactNode } from "react";

import { GroupedList, GroupedListRow } from "../apple/GroupedList";
import { SymbolKachel, type KachelFarbe } from "../apple/SymbolKachel";

export type Variante = "office" | "feld";

export interface ListenEintrag {
  id: string;
  label: ReactNode;
  icon?: LucideIcon;
  /** Nur Feld-Variante: gefüllte Kachel statt nacktem Icon. */
  kachel?: KachelFarbe;
  rechts?: string;
  markiert?: boolean;
  trennerDavor?: boolean;
  kopfDavor?: string;
}

/** Gruppenkopf in Versalien (DESIGN.md: nur für Gruppenüberschriften). */
export function Kopf({ children, variante }: { children: ReactNode; variante: Variante }) {
  return (
    <div
      className={`text-meta font-medium uppercase tracking-wide text-label2 ${
        variante === "feld" ? "px-4 pb-1.5 pt-3" : "px-2 pb-1 pt-1.5"
      }`}
    >
      {children}
    </div>
  );
}

export function zeilenId(listId: string, i: number): string {
  return `${listId}-${i}`;
}

const ZEILE_OFFICE = "flex min-h-[30px] w-full items-center gap-2 rounded-[6px] px-2 text-left text-sekundaer";

/** Reine Darstellung; die Tastatursteuerung kommt vom Eingabefeld (Combobox) oder von `TastaturListe`. */
export function Liste({
  eintraege,
  aktiv,
  onWaehle,
  variante,
  listId,
  ariaLabel,
  navigierbar = false,
  onAktiv,
  wurzelProps,
}: {
  eintraege: ListenEintrag[];
  aktiv: number;
  onWaehle: (id: string) => void;
  variante: Variante;
  listId: string;
  ariaLabel: string;
  navigierbar?: boolean;
  /** Maus über einer Zeile: macht sie zur einzigen hervorgehobenen (gleicher Zustand wie die Tastatur). */
  onAktiv?: (i: number) => void;
  wurzelProps?: React.HTMLAttributes<HTMLDivElement> & { ref?: React.Ref<HTMLDivElement> };
}) {
  if (variante === "office") {
    return (
      <div role="listbox" id={listId} aria-label={ariaLabel} {...wurzelProps}>
        {eintraege.map((e, i) => {
          const Icon = e.icon;
          const hervor = i === aktiv;
          return (
            <div key={e.id}>
              {e.kopfDavor && <Kopf variante="office">{e.kopfDavor}</Kopf>}
              {e.trennerDavor && <div className="my-[5px] h-px bg-sep" />}
              <button
                type="button"
                role="option"
                id={zeilenId(listId, i)}
                aria-selected={!!e.markiert}
                tabIndex={-1}
                onMouseDown={(ev) => ev.preventDefault()}
                onClick={() => onWaehle(e.id)}
                onMouseEnter={() => onAktiv?.(i)}
                onMouseMove={() => !hervor && onAktiv?.(i)}
                className={`${ZEILE_OFFICE} ${
                  hervor ? "bg-tint-solid text-white" : "text-label"
                }`}
              >
                {Icon && <Icon size={15} strokeWidth={2} className={`shrink-0 ${hervor ? "" : "text-label2"}`} aria-hidden="true" />}
                <span className="min-w-0 flex-1 truncate">{e.label}</span>
                {e.rechts && (
                  <span className={`shrink-0 text-meta ${hervor ? "text-white/85" : "text-label2"}`}>
                    {e.rechts}
                  </span>
                )}
                {e.markiert && <Check size={14} strokeWidth={2.5} className="shrink-0" aria-hidden="true" />}
              </button>
            </div>
          );
        })}
      </div>
    );
  }

  const gruppen: { kopf?: string; eintraege: { e: ListenEintrag; i: number }[] }[] = [];
  eintraege.forEach((e, i) => {
    if (gruppen.length === 0 || e.trennerDavor || e.kopfDavor) gruppen.push({ kopf: e.kopfDavor, eintraege: [] });
    gruppen[gruppen.length - 1].eintraege.push({ e, i });
  });
  return (
    <div id={listId} role="group" aria-label={ariaLabel}>
      {gruppen.map((g, gi) => (
        <div key={gi}>
          {g.kopf && <Kopf variante="feld">{g.kopf}</Kopf>}
          <GroupedList className="mx-4 my-3">
            {g.eintraege.map(({ e }, ri) => (
              <GroupedListRow key={e.id} onClick={() => onWaehle(e.id)} last={ri === g.eintraege.length - 1}>
                {e.icon && e.kachel && <SymbolKachel icon={e.icon} farbe={e.kachel} />}
                <span className="min-w-0 flex-1 text-zeile text-label">{e.label}</span>
                {e.rechts && <span className="shrink-0 text-zeile text-label2">{e.rechts}</span>}
                {e.markiert && <Check size={18} strokeWidth={2.5} className="shrink-0 text-tint" aria-hidden="true" />}
                {navigierbar && <ChevronRight size={14} className="shrink-0 text-label3" aria-hidden="true" />}
              </GroupedListRow>
            ))}
          </GroupedList>
        </div>
      ))}
    </div>
  );
}

/** Pfeiltasten/Enter für eine Liste. `start` -1 = nichts vorgewählt (Enter übernimmt dann `ohneAuswahl`). */
export function useListe(anzahl: number, onEnter: (i: number) => void, start = 0, ohneAuswahl?: () => void) {
  const [roh, setAktiv] = useState(start);
  const aktiv = Math.min(roh, anzahl - 1);
  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "ArrowDown" && anzahl > 0) {
      e.preventDefault();
      setAktiv((aktiv + 1) % anzahl);
    } else if (e.key === "ArrowUp" && anzahl > 0) {
      e.preventDefault();
      setAktiv((aktiv - 1 + anzahl) % anzahl);
    } else if (e.key === "Enter") {
      if (aktiv >= 0 && aktiv < anzahl) {
        e.preventDefault();
        onEnter(aktiv);
      } else if (ohneAuswahl) {
        e.preventDefault();
        ohneAuswahl();
      }
    }
  }
  return { aktiv, setAktiv, onKeyDown };
}

/** Liste ohne eigenes Eingabefeld: die Liste selbst nimmt den Fokus und die Tastatur. */
export function TastaturListe({
  eintraege,
  onWaehle,
  onZurueck,
  variante,
  ariaLabel,
  start,
  navigierbar,
}: {
  eintraege: ListenEintrag[];
  onWaehle: (id: string) => void;
  onZurueck?: () => void;
  variante: Variante;
  ariaLabel: string;
  start?: number;
  navigierbar?: boolean;
}) {
  const listId = useId();
  const l = useListe(eintraege.length, (i) => onWaehle(eintraege[i].id), start ?? Math.max(0, eintraege.findIndex((e) => e.markiert)));
  const fokussieren = useCallback((el: HTMLDivElement | null) => el?.focus(), []);
  const office = variante === "office";
  return (
    <Liste
      eintraege={eintraege}
      aktiv={office ? l.aktiv : -1}
      onAktiv={l.setAktiv}
      onWaehle={onWaehle}
      variante={variante}
      listId={listId}
      ariaLabel={ariaLabel}
      navigierbar={navigierbar}
      wurzelProps={
        office
          ? {
              tabIndex: 0,
              ref: fokussieren,
              className: "outline-none!",
              "aria-activedescendant": l.aktiv >= 0 ? zeilenId(listId, l.aktiv) : undefined,
              onKeyDown: (e) => {
                if (e.key === "Backspace") onZurueck?.();
                else l.onKeyDown(e);
              },
            }
          : undefined
      }
    />
  );
}
