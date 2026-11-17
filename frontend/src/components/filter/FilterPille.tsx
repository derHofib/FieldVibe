import { X } from "lucide-react";
import { forwardRef } from "react";

export interface PillenTeile {
  spalte: string;
  operator: string;
  wert: string;
}

type Variante = "office" | "feld";

const RAHMEN_BEARBEITET = "inset 0 0 0 1.5px var(--tint)";

/** Filter-Pille: Spalte, Bedingung und Wert sind einzeln klickbar (öffnen den jeweiligen Schritt), das × entfernt.
 * Text bewusst `text-label`, nicht `text-label2`: auf fill über card nur 3,8:1 im Dunkelmodus. */
export const FilterPille = forwardRef<
  HTMLDivElement,
  {
    teile: PillenTeile;
    variante: Variante;
    /** Pille wird gerade bearbeitet: Tint-Rahmen (inline, sonst gewinnt die Cascade-Layer-Reihenfolge nicht). */
    bearbeitet?: boolean;
    /** Bekommen das geklickte Element als Anker für das Popover. */
    onSpalte: (anker: HTMLElement) => void;
    onOperator: (anker: HTMLElement) => void;
    onWert: (anker: HTMLElement) => void;
    onEntfernen: () => void;
    /** Nur zum Vermessen: gleiche Maße, aber ohne Interaktion und für Hilfstechnik unsichtbar. */
    nurMessen?: boolean;
  }
>(function FilterPille({ teile, variante, bearbeitet, onSpalte, onOperator, onWert, onEntfernen, nurMessen }, ref) {
  const feld = variante === "feld";
  const gruppe = [teile.spalte, teile.operator, teile.wert].filter(Boolean).join(" ");
  const teil = (children: React.ReactNode, onClick: (anker: HTMLElement) => void, klasse: string) =>
    nurMessen ? (
      <span className={`inline-flex h-full items-center whitespace-nowrap ${klasse}`}>{children}</span>
    ) : (
      <button
        type="button"
        onClick={(e) => onClick(e.currentTarget)}
        data-filter-anker
        className={`inline-flex h-full items-center whitespace-nowrap ${klasse}`}
      >
        {children}
      </button>
    );
  return (
    <div
      ref={ref}
      role={nurMessen ? undefined : "group"}
      aria-label={nurMessen ? undefined : `Filter: ${gruppe}`}
      aria-hidden={nurMessen || undefined}
      className={`inline-flex shrink-0 items-center rounded-full bg-fill text-label ${
        feld ? "h-[34px] text-fliess" : "h-7 text-sekundaer"
      }`}
      style={bearbeitet ? { boxShadow: RAHMEN_BEARBEITET } : undefined}
    >
      {teil(teile.spalte, onSpalte, feld ? "pl-3" : "pl-[11px]")}
      {teil(teile.operator, onOperator, "pl-1.5")}
      {teile.wert && teil(teile.wert, onWert, "pl-1.5 font-semibold")}
      {nurMessen ? (
        <span className={`inline-block shrink-0 ${feld ? "mx-1.5 h-[22px] w-[22px]" : "mx-1 h-[18px] w-[18px]"}`} />
      ) : (
        <button
          type="button"
          onClick={onEntfernen}
          aria-label={`Filter ${gruppe} entfernen`}
          className={`flex shrink-0 items-center justify-center ${
            feld ? "mx-0.5 h-11 w-11 -my-[5px]" : "mx-1 h-[18px] w-[18px]"
          }`}
        >
          <span
            className={`flex items-center justify-center rounded-full bg-fill2 text-label2 ${
              feld ? "h-[22px] w-[22px]" : "h-[18px] w-[18px]"
            }`}
          >
            <X size={feld ? 11 : 10} strokeWidth={3} aria-hidden="true" />
          </span>
        </button>
      )}
    </div>
  );
});

/** Entwurfs-Pille beim Anlegen: zeigt die bisher gewählten Teile, Tint-Rahmen statt Füllung. */
export function EntwurfsPille({ teile }: { teile: Partial<PillenTeile> }) {
  return (
    <div
      className="inline-flex h-7 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full bg-card px-[11px] text-sekundaer text-label"
      style={{ boxShadow: RAHMEN_BEARBEITET }}
      aria-hidden="true"
    >
      {teile.spalte && <span>{teile.spalte}</span>}
      {teile.operator && <span>{teile.operator}</span>}
      {teile.wert && <span className="font-semibold">{teile.wert}</span>}
    </div>
  );
}
