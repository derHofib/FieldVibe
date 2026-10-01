import { Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import type { ZeitplanAbhaengigkeit, ZeitplanAbhaengigkeitArt } from "../../../types";
import { ART_ERKLAERUNG, ART_LABEL } from "./zeitplanLogik";

const ARTEN: ZeitplanAbhaengigkeitArt[] = ["ende_anfang", "anfang_anfang", "ende_ende"];

/** Kleines Popover an einer Verbindungslinie: Art, Versatz in Tagen (auch
 * negativ) und Loeschen. Position in Viewport-Koordinaten (fixed, Portal),
 * damit das Scroll-Gebiet des Gantt es nicht abschneidet. */
export function VerbindungsPopover({
  abhaengigkeit,
  position,
  vorgaengerTitel,
  nachfolgerTitel,
  onVersatz,
  onArt,
  onLoeschen,
  onClose,
}: {
  abhaengigkeit: ZeitplanAbhaengigkeit;
  position: { x: number; y: number };
  vorgaengerTitel: string;
  nachfolgerTitel: string;
  onVersatz: (tage: number) => void;
  onArt: (art: ZeitplanAbhaengigkeitArt) => void;
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
      className="fixed z-[60] w-[280px] rounded-[10px] border-[0.5px] p-3"
      style={{
        top: Math.max(8, Math.min(position.y + 8, window.innerHeight - 420)),
        left: Math.min(Math.max(8, position.x - 140), window.innerWidth - 288),
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
      <p id="zeitplan-art-label" className="mb-1 text-[11px] font-bold tracking-wide text-label3 uppercase">
        Art der Verbindung
      </p>
      <div role="radiogroup" aria-labelledby="zeitplan-art-label" className="mb-3 space-y-1">
        {ARTEN.map((art) => {
          const aktiv = (abhaengigkeit.art ?? "ende_anfang") === art;
          return (
            <button
              key={art}
              type="button"
              role="radio"
              aria-checked={aktiv}
              onClick={() => !aktiv && onArt(art)}
              className={`block w-full rounded-[8px] px-2 py-1.5 text-left ${aktiv ? "bg-tintbg" : "hover:bg-fill"}`}
            >
              <span className={`flex items-center gap-1.5 text-[13px] font-semibold ${aktiv ? "text-tint-text" : "text-label"}`}>
                <span
                  aria-hidden="true"
                  className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border ${aktiv ? "border-tint" : "border-sepstrong"}`}
                >
                  {aktiv && <span className="h-2 w-2 rounded-full bg-tint" />}
                </span>
                {ART_LABEL[art]}
              </span>
              <span className="block pl-5 text-[11px] text-label2">{ART_ERKLAERUNG[art]}</span>
            </button>
          );
        })}
      </div>
      <label className="mb-1 block text-[11px] font-bold tracking-wide text-label3 uppercase" htmlFor="zeitplan-versatz">
        Versatz in Tagen
      </label>
      <input
        id="zeitplan-versatz"
        type="number"
        step={1}
        value={wert}
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
