import { Check, ChevronDown, ChevronsDownUp, ChevronsUpDown, Rows3 } from "lucide-react";
import { useState } from "react";

import { GroupedList, GroupedListRow } from "../apple/GroupedList";
import { PulldownMenu, type PulldownItem } from "../apple/PulldownMenu";
import { Sheet } from "../apple/Sheet";
import type { LucideIcon } from "lucide-react";

export interface GruppierOption<T extends string> {
  wert: T;
  label: string;
  icon?: LucideIcon;
}

interface Props<T extends string> {
  /** Aktuelle Gruppierung; `keinWert` steht für "Nicht gruppieren". */
  wert: T;
  optionen: GruppierOption<T>[];
  keinWert: T;
  onWechsel: (wert: T) => void;
  /** Ohne diese Funktionen entfällt der Eintrag "Alle Gruppen einklappen/ausklappen". */
  onAlleEinklappen?: () => void;
  onAlleAusklappen?: () => void;
  alleEingeklappt?: boolean;
  variante?: "office" | "feld";
}

/** Auswahl der Gruppierung einer Liste (eine Ebene). Office: Pulldown mit "Gruppieren: X"; Feld: Knopf, der ein
 * Sheet mit denselben Optionen öffnet. Bewusst ohne Wissen über die Seite, damit andere Listen es nutzen können. */
export function GruppierenMenue<T extends string>(props: Props<T>) {
  const { wert, optionen, keinWert, onWechsel, onAlleEinklappen, onAlleAusklappen, alleEingeklappt = false, variante = "office" } = props;
  const aktuell = wert === keinWert ? null : optionen.find((o) => o.wert === wert);
  const gruppiert = !!aktuell;

  if (variante === "feld") return <FeldVariante {...props} gruppiert={gruppiert} />;

  const items: PulldownItem[] = optionen.map((o) => ({
    label: o.label,
    icon: o.icon,
    aktiv: o.wert === wert,
    onSelect: () => onWechsel(o.wert),
  }));
  items.push("trenner", { label: "Nicht gruppieren", aktiv: wert === keinWert, onSelect: () => onWechsel(keinWert) });
  if (gruppiert && onAlleEinklappen && onAlleAusklappen) {
    items.push("trenner", {
      label: alleEingeklappt ? "Alle Gruppen ausklappen" : "Alle Gruppen einklappen",
      icon: alleEingeklappt ? ChevronsUpDown : ChevronsDownUp,
      onSelect: alleEingeklappt ? onAlleAusklappen : onAlleEinklappen,
    });
  }

  return (
    <PulldownMenu
      ariaLabel="Gruppieren"
      items={items}
      ausrichtung="rechts"
      trigger={({ toggeln, triggerRef, offen }) => (
        <button
          ref={triggerRef}
          type="button"
          onClick={toggeln}
          aria-haspopup="menu"
          aria-expanded={offen}
          className="flex h-7 items-center gap-1.5 rounded-[7px] px-1.5 text-sekundaer font-medium text-label hover:bg-fill"
        >
          <Rows3 size={15} strokeWidth={2} className="shrink-0" aria-hidden="true" />
          <span className="whitespace-nowrap">Gruppieren: {aktuell?.label ?? "Keine"}</span>
          <ChevronDown size={14} strokeWidth={2} className="shrink-0 text-label2" aria-hidden="true" />
        </button>
      )}
    />
  );
}

function FeldVariante<T extends string>({
  wert,
  optionen,
  keinWert,
  onWechsel,
  onAlleEinklappen,
  onAlleAusklappen,
  alleEingeklappt = false,
  gruppiert,
}: Props<T> & { gruppiert: boolean }) {
  const [offen, setOffen] = useState(false);
  const waehle = (w: T) => {
    onWechsel(w);
    setOffen(false);
  };
  const zeilen: { key: string; label: string; icon?: LucideIcon; aktiv?: boolean; onClick: () => void }[] = [
    ...optionen.map((o) => ({ key: o.wert, label: o.label, icon: o.icon, aktiv: o.wert === wert, onClick: () => waehle(o.wert) })),
    { key: "keine", label: "Nicht gruppieren", aktiv: wert === keinWert, onClick: () => waehle(keinWert) },
  ];
  const einklappen = gruppiert && onAlleEinklappen && onAlleAusklappen;

  return (
    <>
      <button
        type="button"
        onClick={() => setOffen(true)}
        aria-haspopup="dialog"
        aria-label="Gruppieren"
        title="Gruppieren"
        // Aktiv in Tint, solange gruppiert wird -- wie der Filter-Knopf daneben.
        className={`flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full ${
          gruppiert ? "bg-tintbg text-tint-text" : "bg-card text-label2"
        }`}
      >
        <Rows3 size={17} strokeWidth={2} aria-hidden="true" />
      </button>
      <Sheet
        offen={offen}
        onClose={() => setOffen(false)}
        titel="Gruppieren"
        links={
          <button type="button" onClick={() => setOffen(false)} className="text-zeile text-tint-text">
            Fertig
          </button>
        }
      >
        <div className="space-y-4 p-4">
          <GroupedList>
            {zeilen.map((z, i) => (
              <GroupedListRow key={z.key} onClick={z.onClick} last={i === zeilen.length - 1}>
                {z.icon && <z.icon size={18} strokeWidth={2} className="shrink-0 text-label2" aria-hidden="true" />}
                <span className="flex-1 text-zeile text-label">{z.label}</span>
                {z.aktiv && <Check size={18} strokeWidth={2.5} className="shrink-0 text-tint" aria-label="Ausgewählt" />}
              </GroupedListRow>
            ))}
          </GroupedList>
          {einklappen && (
            <GroupedList>
              <GroupedListRow
                last
                onClick={() => {
                  (alleEingeklappt ? onAlleAusklappen : onAlleEinklappen)();
                  setOffen(false);
                }}
              >
                <span className="flex-1 text-zeile text-tint-text">
                  {alleEingeklappt ? "Alle Gruppen ausklappen" : "Alle Gruppen einklappen"}
                </span>
              </GroupedListRow>
            </GroupedList>
          )}
        </div>
      </Sheet>
    </>
  );
}
