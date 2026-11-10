import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";

/** Gruppierte Liste (Abschnitt 4.2, Mobil): Container mit Außenabstand 16
 * seitlich -- der Aufrufer platziert das Element selbst im Layout, diese
 * Komponente kuemmert sich nur um Flaeche/Radius/Ueberlauf. */
export function GroupedList({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`overflow-hidden rounded-[var(--radius-ap-card)] bg-cell ${className}`}>{children}</div>;
}

/** Eine Zeile einer gruppierten Liste. `last` unterdrueckt die Trennlinie
 * (letzte Zeile hat keine). Die Trennlinie ist links eingerueckt (beginnt
 * am Textanfang), nicht am Zellenrand -- absolut positioniert statt per
 * Rahmen, damit sie unabhaengig vom Zeileninhalt exakt bei 16px startet. */
export function GroupedListRow({
  children,
  onClick,
  navigierbar = false,
  last = false,
  minHoehe = 44,
}: {
  children: ReactNode;
  onClick?: () => void;
  navigierbar?: boolean;
  last?: boolean;
  minHoehe?: number;
}) {
  const Comp = onClick ? "button" : "div";
  return (
    <Comp
      type={onClick ? "button" : undefined}
      onClick={onClick}
      className={`relative flex w-full items-center gap-3 py-2.5 pr-4 pl-4 text-left ${onClick ? "active:bg-fill" : ""}`}
      style={{ minHeight: minHoehe }}
    >
      <div className="flex min-w-0 flex-1 items-center gap-3">{children}</div>
      {navigierbar && <ChevronRight size={14} className="shrink-0 text-label3" aria-hidden="true" />}
      {!last && <span className="absolute right-0 bottom-0 left-4 h-px bg-sep" aria-hidden="true" />}
    </Comp>
  );
}

/** Wert-Zeile (Abschnitt 4.2): Label links, Wert rechts in --label2. */
export function GroupedListValueRow({ label, wert, last = false }: { label: string; wert: ReactNode; last?: boolean }) {
  return (
    <GroupedListRow last={last}>
      <span className="flex-1 text-[17px] text-label">{label}</span>
      <span className="shrink-0 text-[17px] text-label2">{wert}</span>
    </GroupedListRow>
  );
}
