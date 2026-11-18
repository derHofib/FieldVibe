import { Sparkles } from "lucide-react";

/** Kennzeichnung "von Claude" (MCP) -- violett (st-wartet-Töne), weil Violett in
 * Formularen keine Statusbedeutung trägt (Blau = Tint, Grün = erledigt). Das
 * Symbol steht dabei, damit die Marke nicht nur über die Farbe lesbar ist. */
export function ClaudeMarke({ label = "Claude", klein = false }: { label?: string; klein?: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-[var(--radius-ap-pill)] bg-st-wartet-bg px-2 py-0.5 font-semibold text-st-wartet ${
        klein ? "text-meta" : "text-sekundaer"
      }`}
    >
      <Sparkles size={klein ? 11 : 12} strokeWidth={2} aria-hidden="true" />
      {label}
    </span>
  );
}
