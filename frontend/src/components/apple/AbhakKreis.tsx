import { Check } from "lucide-react";

/** Abhak-Kreis (Abschnitt 4.2) fuer Taetigkeiten/Checklisten. */
export function AbhakKreis({
  checked,
  onChange,
  ariaLabel,
}: {
  checked: boolean;
  onChange: (wert: boolean) => void;
  ariaLabel: string;
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      aria-label={ariaLabel}
      onClick={() => onChange(!checked)}
      className="flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full"
      style={{
        border: checked ? "none" : "1.5px solid var(--label3)",
        backgroundColor: checked ? "var(--tint)" : "transparent",
      }}
    >
      {checked && <Check size={14} strokeWidth={3} className="text-white" />}
    </button>
  );
}
