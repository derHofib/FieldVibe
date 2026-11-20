import { useEffect, useRef } from "react";

/** Lädt die nächste Seite, sobald der Anker ins Bild scrollt; die Schaltfläche ist der Rückfall ohne IntersectionObserver. */
export function NachladenAnker({
  onSichtbar,
  laeuft,
  feld = false,
}: {
  onSichtbar: () => void;
  laeuft: boolean;
  feld?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const callback = useRef(onSichtbar);
  callback.current = onSichtbar;

  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined" || laeuft) return;
    const beobachter = new IntersectionObserver((eintraege) => {
      if (eintraege.some((e) => e.isIntersecting)) callback.current();
    });
    beobachter.observe(el);
    return () => beobachter.disconnect();
  }, [laeuft]);

  return (
    <div ref={ref} role="presentation" className="flex justify-center py-2">
      <button
        type="button"
        tabIndex={-1}
        disabled={laeuft}
        onMouseDown={(e) => e.preventDefault()}
        onClick={onSichtbar}
        className={`text-sekundaer font-medium text-tint-text disabled:opacity-50 ${feld ? "btn-touch" : ""}`}
      >
        {laeuft ? "Lädt …" : "Weitere anzeigen"}
      </button>
    </div>
  );
}
