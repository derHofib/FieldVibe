import type { ReactNode } from "react";

import { istOfficeHost } from "../office/hostname";
import { Sheet } from "./apple/Sheet";
import { SeitenPanel } from "./SeitenPanel";

/**
 * Einheitliche Hülle für "Neu anlegen"-Formulare: Sheet in der Feld-App,
 * Seitenpanel im Office. Ersetzt das inline aufklappende Formular über der
 * Liste. Der Inhalt bringt seinen eigenen Innenabstand mit (p-4).
 */
export function AnlegenPanel({
  offen,
  titel,
  onClose,
  children,
}: {
  offen: boolean;
  titel: string;
  onClose: () => void;
  children: ReactNode;
}) {
  if (!offen) return null;
  if (istOfficeHost()) {
    return (
      <SeitenPanel title={titel} onClose={onClose}>
        {children}
      </SeitenPanel>
    );
  }
  return (
    <Sheet
      offen
      titel={titel}
      onClose={onClose}
      links={
        <button type="button" onClick={onClose} className="text-[17px] text-tint-text">
          Abbrechen
        </button>
      }
    >
      {children}
    </Sheet>
  );
}
