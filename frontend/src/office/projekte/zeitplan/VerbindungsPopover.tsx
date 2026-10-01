import { Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import type { ZeitplanAbhaengigkeit } from "../../../types";

/** Kleines Popover an einer Verbindungslinie: Versatz in Tagen (auch
 * negativ) und Loeschen. Position in Viewport-Koordinaten (fixed, Portal),
 * damit das Scroll-Gebiet des Gantt es nicht abschneidet. */
export function VerbindungsPopover({
  abhaengigkeit,
  position,
  vorgaengerTitel,
  nachfolgerTitel,
  onVersatz,
  onLoeschen,
  onClose,
}: {
  abhaengigkeit: ZeitplanAbhaengigkeit;
  position: { x: number; y: number };
  vorgaengerTitel: string;
  nachfolgerTitel: string;
  onVersatz: (tage: number) => void;
  onLoeschen: () => void;
  onClose: () => void;
}) {
  const [wert, setWert] = useState(String(abhaengigkeit.versatz_tage));
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function aufKlick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    function aufTaste(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      e.stopPropagation(); // Capture-Phase: sonst schliesst Esc auch das Seitenpanel
      onClose();
    }
    document.addEventListener("mousedown", aufKlick);
    document.addEventListener("keydown", aufTaste, true);
    return () => {
      document.removeEventListener("mousedown", aufKlick);
      document.removeEventListener("keydown", aufTaste, true);
    };
  }, [onClose]);

  function speichern() {
    const n = Math.trunc(Number(wert));
    if (wert.trim() === "" || !Number.isFinite(n)) {
      setWert(String(abhaengigkeit.versatz_tage));
      return;
    }
    if (n !== abhaengigkeit.versatz_tage) onVersatz(n);
  }

  return createPortal(
    <div
      ref={ref}
      role="dialog"
      aria-label="Verbindung bearbeiten"
      className="fixed z-[60] w-[260px] rounded-[10px] border-[0.5px] p-3"
      style={{
        top: Math.min(position.y + 8, window.innerHeight - 190),
        left: Math.min(Math.max(8, position.x - 130), window.innerWidth - 268),
        backgroundColor: "var(--menu)",
        backdropFilter: "blur(30px)",
        WebkitBackdropFilter: "blur(30px)",
        borderColor: "var(--sepstrong)",
        boxShadow: "0 10px 30px rgba(0,0,0,.22)",
      }}
    >
      <p className="mb-2 truncate text-xs text-label2">
        {vorgaengerTitel} → {nachfolgerTitel}
      </p>
      <label className="mb-1 block text-[11px] font-bold tracking-wide text-label3 uppercase" htmlFor="zeitplan-versatz">
        Versatz in Tagen
      </label>
      <input
        id="zeitplan-versatz"
        type="number"
        step={1}
        value={wert}
        autoFocus
        onChange={(e) => setWert(e.target.value)}
        onBlur={speichern}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            speichern();
            onClose();
          }
        }}
        className="field-ap"
      />
      <p className="mt-1.5 text-[11px] text-label2">+2 = 2 Tage Wartezeit, −1 = 1 Tag Überlappung</p>
      <button
        type="button"
        onClick={onLoeschen}
        className="mt-2 flex h-[30px] w-full items-center gap-2 rounded-[6px] px-2 text-[13px] text-st-fehlt hover:bg-st-fehlt-bg"
      >
        <Trash2 size={15} strokeWidth={2} aria-hidden="true" />
        Verbindung löschen
      </button>
    </div>,
    document.body,
  );
}
