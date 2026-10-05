import {
  Archive,
  CopyPlus,
  Eye,
  FileText,
  GitBranchPlus,
  KeyRound,
  Plus,
  SquareDashed,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

import { KONTEXT_AKTION_LABEL, type KontextAktion } from "./darstellung";

const ICON: Record<KontextAktion, LucideIcon> = {
  details: FileText,
  darunter: Plus,
  platzhalter: SquareDashed,
  stabsstelle: GitBranchPlus,
  duplizieren: CopyPlus,
  rechte: KeyRound,
  anzeigen_als: Eye,
  archivieren: Archive,
  loeschen: Trash2,
};

const MENUE_BREITE = 248;

/** Kontextmenue eines Knotens (Rechtsklick oder "..."-Button). Zeigt nur die uebergebenen Aktionen. */
export function PositionKontextMenue({
  anker,
  aktionen,
  onWahl,
  onClose,
}: {
  anker: { x: number; y: number };
  aktionen: KontextAktion[];
  onWahl: (aktion: KontextAktion) => void;
  onClose: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    itemRefs.current[0]?.focus();
    function aufKlick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) onClose();
    }
    function aufTaste(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    }
    document.addEventListener("mousedown", aufKlick);
    document.addEventListener("keydown", aufTaste, true);
    return () => {
      document.removeEventListener("mousedown", aufKlick);
      document.removeEventListener("keydown", aufTaste, true);
    };
  }, [onClose]);

  function aufTastatur(e: React.KeyboardEvent) {
    const aktuell = itemRefs.current.findIndex((el) => el === document.activeElement);
    const n = aktionen.length;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      itemRefs.current[(aktuell + 1) % n]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      itemRefs.current[(aktuell - 1 + n) % n]?.focus();
    }
  }

  const links = Math.max(8, Math.min(anker.x, window.innerWidth - MENUE_BREITE - 8));
  const oben = Math.max(8, Math.min(anker.y, window.innerHeight - (aktionen.length * 30 + 16) - 8));

  return createPortal(
    <div
      ref={panelRef}
      role="menu"
      aria-label="Aktionen für die Position"
      onKeyDown={aufTastatur}
      className="fixed z-[60] rounded-[10px] border-[0.5px] p-[5px]"
      style={{
        top: oben,
        left: links,
        width: MENUE_BREITE,
        backgroundColor: "var(--menu)",
        backdropFilter: "blur(30px)",
        WebkitBackdropFilter: "blur(30px)",
        borderColor: "var(--sepstrong)",
        boxShadow: "0 10px 30px rgba(0,0,0,.22)",
      }}
    >
      {aktionen.map((aktion, i) => {
        const Icon = ICON[aktion];
        const gefaehrlich = aktion === "loeschen";
        return (
          <div key={aktion}>
            {(aktion === "archivieren" || aktion === "anzeigen_als") && i > 0 && <div className="my-[5px] h-px bg-sep" />}
            <button
              ref={(el) => {
                itemRefs.current[i] = el;
              }}
              role="menuitem"
              type="button"
              onClick={() => onWahl(aktion)}
              className={`flex h-[30px] w-full items-center gap-2 rounded-[6px] px-2 text-left hover:bg-tint-solid hover:text-white focus-visible:bg-tint-solid focus-visible:text-white focus-visible:outline-none ${
                gefaehrlich ? "text-st-fehlt" : "text-label"
              }`}
            >
              <Icon size={15} strokeWidth={2} className="shrink-0" aria-hidden="true" />
              <span className="flex-1 text-[13px]">{KONTEXT_AKTION_LABEL[aktion]}</span>
            </button>
          </div>
        );
      })}
    </div>,
    document.body,
  );
}
