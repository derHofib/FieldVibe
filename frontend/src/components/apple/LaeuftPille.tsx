/** Einziger Einsatz des Logo-Grüns: "läuft gerade" (laufende Zeiterfassung).
 * Farbe trägt die Aussage nie allein -- Text "Läuft" und der pulsierende
 * Punkt sind Pflicht. Pulsieren nur ohne prefers-reduced-motion, sonst
 * bliebe der Punkt im Endzustand der Animation halbtransparent stehen. */
export function LaeuftPunkt({ className = "" }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      data-testid="laeuft-punkt"
      className={`inline-block h-2 w-2 shrink-0 rounded-full bg-live motion-safe:animate-livepulse ${className}`}
    />
  );
}

export function LaeuftPille({ label = "Läuft", className = "" }: { label?: string; className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-[5px] rounded-[var(--radius-ap-pill)] bg-live-bg px-2 py-0.5 text-meta font-semibold text-live-text ${className}`}
    >
      <LaeuftPunkt />
      {label}
    </span>
  );
}
