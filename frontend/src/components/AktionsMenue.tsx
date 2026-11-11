import type { LucideIcon } from "lucide-react";
import { MoreHorizontal } from "lucide-react";
import type { ReactNode } from "react";

import { PulldownMenu, type PulldownItem } from "./apple/PulldownMenu";

export interface AktionsMenueEintrag {
  label: string;
  icon?: LucideIcon;
  onClick: () => void | Promise<void>;
  /** Destruktive Aktionen stehen am Ende und sind rot gekennzeichnet. */
  destruktiv?: boolean;
  disabled?: boolean;
}

/** Zeilen-/Nutzermenü: dünner Rahmen um das bestehende PulldownMenu
 * (components/apple) mit Drei-Punkte-Standardauslöser. */
export function AktionsMenue({
  eintraege,
  label,
  ausloeser,
  richtung,
}: {
  eintraege: (AktionsMenueEintrag | "trenner")[];
  label: string;
  /** Eigener Auslöser; Standard ist ein Drei-Punkte-Button. */
  ausloeser?: (props: { offen: boolean }) => ReactNode;
  richtung?: "unten" | "oben";
}) {
  const items: PulldownItem[] = eintraege.map((e) =>
    e === "trenner" ? e : { ...e, onSelect: e.onClick },
  );
  return (
    <PulldownMenu
      ariaLabel={label}
      richtung={richtung}
      items={items}
      trigger={({ offen, toggeln, triggerRef }) => (
        <button
          ref={triggerRef}
          type="button"
          onClick={toggeln}
          aria-label={label}
          title={label}
          aria-haspopup="menu"
          aria-expanded={offen}
          className={ausloeser ? "block w-full" : "btn-ap-toolbar"}
        >
          {ausloeser ? ausloeser({ offen }) : <MoreHorizontal size={16} strokeWidth={2} />}
        </button>
      )}
    />
  );
}
