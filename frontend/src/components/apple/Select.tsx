import { ChevronDown } from "lucide-react";
import { forwardRef, type SelectHTMLAttributes } from "react";

type SelectProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, "className"> & {
  /** Breitenklasse für den Wrapper (z. B. "w-auto", "w-20"); Default volle Breite. */
  className?: string;
  /** "kompakt" für Filterleisten/Tabellenzeilen (ab md 32px/13px). */
  groesse?: "normal" | "kompakt";
  /** "transparent" für Felder auf einer Füllfläche (bg-fill), damit sie wie die übrigen Felder dort aussehen. */
  flaeche?: "card" | "transparent";
};

/** Nativer Select im Stil von .field-ap mit eigenem Chevron. Der native
 * Picker bleibt erhalten (Mobil-Wheel, Tastatur, Screenreader). */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className = "w-full", groesse = "normal", flaeche = "card", children, ...rest },
  ref,
) {
  return (
    <span className={`relative inline-block ${className}`}>
      <select
        ref={ref}
        className={`select-ap ${groesse === "kompakt" ? "select-ap-kompakt" : ""} ${flaeche === "transparent" ? "select-ap-transparent" : ""}`}
        {...rest}
      >
        {children}
      </select>
      <ChevronDown
        size={16}
        strokeWidth={2}
        aria-hidden="true"
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-label2"
      />
    </span>
  );
});
