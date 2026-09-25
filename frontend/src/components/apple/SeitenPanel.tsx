import { X } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

const STORAGE_KEY = "fieldvibe_seitenpanel_breite";
const BREITE_STANDARD = 480;
const BREITE_MIN = 360;
const BREITE_MAX = 1100;

function gespeicherteBreite(): number {
  try {
    const roh = localStorage.getItem(STORAGE_KEY);
    const wert = roh ? Number(roh) : NaN;
    if (Number.isFinite(wert) && wert >= BREITE_MIN && wert <= BREITE_MAX) return wert;
  } catch {
    // Privater Modus o.ae. -- Standardbreite reicht als Fallback.
  }
  return BREITE_STANDARD;
}

/** Rechtes, mit der Maus breiter ziehbares Detail-Panel (Projekte/
 * Auftraege-Tabellen, siehe office/auftraege/ und office/projekte/) --
 * im Unterschied zu Sheet.tsx (zentrierter Dialog fixer Breite) bleibt
 * hier die Tabelle links sichtbar, das Panel schiebt sich als Overlay
 * von rechts rein. Die Breite wird nur als Browser-Komfort im
 * localStorage gemerkt (kein Sync zwischen Geraeten/Nutzern noetig). */
export function SeitenPanel({
  offen,
  onClose,
  titel,
  aktionen,
  children,
}: {
  offen: boolean;
  onClose: () => void;
  titel: string;
  aktionen?: ReactNode;
  children: ReactNode;
}) {
  const [breite, setBreite] = useState(gespeicherteBreite);
  const ziehtGerade = useRef(false);

  useEffect(() => {
    if (!offen) return;
    function aufTaste(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", aufTaste);
    return () => document.removeEventListener("keydown", aufTaste);
  }, [offen, onClose]);

  const ziehenStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    ziehtGerade.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    function aufBewegen(ev: MouseEvent) {
      if (!ziehtGerade.current) return;
      const neueBreite = Math.min(BREITE_MAX, Math.max(BREITE_MIN, window.innerWidth - ev.clientX));
      setBreite(neueBreite);
    }
    function aufLoslassen() {
      ziehtGerade.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      window.removeEventListener("mousemove", aufBewegen);
      window.removeEventListener("mouseup", aufLoslassen);
      setBreite((aktuell) => {
        try {
          localStorage.setItem(STORAGE_KEY, String(aktuell));
        } catch {
          // Kein dauerhafter Schaden, wenn das Merken der Breite fehlschlaegt.
        }
        return aktuell;
      });
    }
    window.addEventListener("mousemove", aufBewegen);
    window.addEventListener("mouseup", aufLoslassen);
  }, []);

  if (!offen) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={titel}
        onClick={(e) => e.stopPropagation()}
        style={{ width: breite }}
        className="ap-sheet-surface relative flex h-full max-w-full flex-col bg-gbg shadow-xl"
      >
        {/* Ziehgriff: 6px breiter Hit-Bereich am linken Rand, damit er auch
            ohne Pixel-genaues Treffen der 1px-Trennlinie greifbar ist. */}
        <div
          onMouseDown={ziehenStart}
          role="separator"
          aria-orientation="vertical"
          aria-label="Panel-Breite ändern"
          className="absolute top-0 bottom-0 left-0 z-10 -ml-[3px] w-[6px] cursor-col-resize hover:bg-tint/30"
        />
        <div className="flex items-center border-b-[0.5px] border-sep px-4 py-3">
          <h2 className="flex-1 truncate text-[17px] font-semibold text-label">{titel}</h2>
          <div className="flex items-center gap-2">
            {aktionen}
            <button
              onClick={onClose}
              aria-label="Panel schließen"
              className="btn-touch rounded-full p-1.5 text-label2 hover:bg-fill hover:text-label"
            >
              <X size={18} strokeWidth={2} aria-hidden="true" />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
