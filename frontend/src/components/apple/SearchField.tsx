import { Mic, Search } from "lucide-react";

/** Suchfeld (Abschnitt 4.2): randlos, Fuellung statt Rahmen. Mobil-Variante
 * zusaetzlich mit Mikrofon-Symbol rechts. */
export function SearchField({
  value,
  onChange,
  placeholder = "Suchen",
  groesse = "desktop",
  onMikrofon,
  ariaLabel = "Suchen",
  className = "",
}: {
  value: string;
  onChange: (wert: string) => void;
  placeholder?: string;
  groesse?: "desktop" | "mobil";
  onMikrofon?: () => void;
  ariaLabel?: string;
  className?: string;
}) {
  const mobil = groesse === "mobil";
  return (
    <div
      className={`search-ap ${mobil ? "h-9 px-2.5" : "h-7 px-2"} ${className}`}
      style={{ borderRadius: mobil ? 10 : "var(--radius-ap-input)" }}
    >
      <Search size={mobil ? 17 : 14} strokeWidth={2} className="shrink-0 text-label2" aria-hidden="true" />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel}
        className={`search-ap-input ${mobil ? "text-[17px]" : "text-[13px]"}`}
      />
      {mobil && onMikrofon && (
        <button type="button" onClick={onMikrofon} aria-label="Spracheingabe" className="shrink-0 text-label2">
          <Mic size={17} strokeWidth={2} />
        </button>
      )}
    </div>
  );
}
