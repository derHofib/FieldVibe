import { useEffect, useRef, useState } from "react";

export interface SearchableSelectOption {
  value: string;
  label: string;
  sublabel?: string;
}

/** Tippbares Auswahlfeld: zeigt beim Fokussieren alle Optionen, filtert sie
 * live nach eingegebenem Text (Substring-Match auf label, ohne
 * Gross-/Kleinschreibung) -- ersetzt ein reines <select>, sobald die
 * Optionsliste zu lang ist, um sie blind durchzuscrollen (z.B. der
 * Material-Katalog). */
export function SearchableSelect({
  options,
  value,
  onChange,
  placeholder = "Auswählen…",
  className = "",
  id,
}: {
  options: SearchableSelectOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  id?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const selected = options.find((o) => o.value === value);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const gefiltert = query
    ? options.filter((o) => o.label.toLowerCase().includes(query.toLowerCase()))
    : options;

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <input
        id={id}
        type="text"
        value={open ? query : (selected?.label ?? "")}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => {
          setOpen(true);
          setQuery("");
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            // Nur die Auswahl schließen, nicht ein umgebendes Panel
            e.stopPropagation();
            setOpen(false);
            setQuery("");
            e.currentTarget.blur();
          }
        }}
        placeholder={placeholder}
        className="field-ap"
      />
      {open && (
        <div className="absolute z-10 mt-1 max-h-56 w-full overflow-y-auto rounded-[var(--radius-ap-md)] border border-sep bg-card shadow-lg">
          {gefiltert.length === 0 ? (
            <p className="px-2 py-1.5 text-sekundaer text-label2">Keine Treffer</p>
          ) : (
            gefiltert.map((o) => (
              <button
                type="button"
                key={o.value}
                onClick={() => {
                  onChange(o.value);
                  setOpen(false);
                  setQuery("");
                }}
                className={`btn-touch block w-full px-2 py-1.5 text-left text-sekundaer hover:bg-fill ${
                  o.value === value ? "bg-fill font-medium" : ""
                }`}
              >
                {o.label}
                {o.sublabel && (
                  <span className="ml-1.5 text-sekundaer text-label2">{o.sublabel}</span>
                )}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
