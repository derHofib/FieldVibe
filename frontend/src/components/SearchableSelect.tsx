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
}: {
  options: SearchableSelectOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
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
            setOpen(false);
            setQuery("");
            e.currentTarget.blur();
          }
        }}
        placeholder={placeholder}
        className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
      />
      {open && (
        <div className="absolute z-10 mt-1 max-h-56 w-full overflow-y-auto rounded-md border border-slate-200 bg-white shadow-lg dark:border-stone-700 dark:bg-stone-800">
          {gefiltert.length === 0 ? (
            <p className="px-2 py-1.5 text-sm text-ind-ink-3">Keine Treffer</p>
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
                className={`btn-touch block w-full px-2 py-1.5 text-left text-sm hover:bg-slate-100 dark:hover:bg-stone-700 ${
                  o.value === value ? "bg-slate-50 font-medium dark:bg-stone-700/60" : ""
                }`}
              >
                {o.label}
                {o.sublabel && (
                  <span className="ml-1.5 text-xs text-ind-ink-3">{o.sublabel}</span>
                )}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
